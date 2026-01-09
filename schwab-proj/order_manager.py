from schwab.auth import easy_client
from schwab.client import Client
from schwab.orders.common import OrderType, Duration
from schwab.orders.equities import equity_sell_limit
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from config import load_trading_config, setup_logging, load_logging_config, validate_environment

# Initialize logging
logging_config = load_logging_config()
logger = setup_logging(logging_config, 'trading.log')

@dataclass
class MarketData:
    """Container for market data""" 
    symbol: str
    highs: List[float]
    lows: List[float]
    closes: List[float]
    
    def __post_init__(self):
        if not (len(self.highs) == len(self.lows) == len(self.closes)):
            raise ValueError("All price lists must have the same length")

class TechnicalIndicators:
    """Calculate technical indicators for trading signals"""
    
    @staticmethod
    def simple_moving_average(prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            raise ValueError(f"Not enough data points. Need {period}, got {len(prices)}")
        return sum(prices[-period:]) / period
    
    @staticmethod
    def exponential_moving_average(prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            raise ValueError(f"Not enough data points. Need {period}, got {len(prices)}")
        
        alpha = 2 / (period + 1)
        ema = prices[-period]  # seed with first value of window
        
        for price in prices[-period+1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    @staticmethod
    def average_true_range(market_data: MarketData, period: int) -> float:
        """Calculate Average True Range"""
        if len(market_data.closes) < period + 1:  # +1 because we need previous close
            raise ValueError(f"Not enough data points. Need {period + 1}, got {len(market_data.closes)}")
        
        true_ranges = []
        for i in range(1, len(market_data.closes)):
            tr = max(
                market_data.highs[i] - market_data.lows[i],
                abs(market_data.highs[i] - market_data.closes[i-1]),
                abs(market_data.lows[i] - market_data.closes[i-1])
            )
            true_ranges.append(tr)
        
        return sum(true_ranges[-period:]) / period
    
    @staticmethod
    def chandelier_exit(market_data: MarketData, period: int, multiplier: float) -> float:
        """Calculate Chandelier Exit"""
        if len(market_data.highs) < period:
            raise ValueError(f"Not enough data points. Need {period}, got {len(market_data.highs)}")
        
        highest_high = max(market_data.highs[-period:])
        atr = TechnicalIndicators.average_true_range(market_data, 10)  
        
        return highest_high - multiplier * atr

class TradingManager:
    """Main trading logic manager"""
    
    def __init__(self, config):
        self.config = config
        self.client = self._initialize_client()
        self.account_hash = self._get_account_hash()
        
    def _initialize_client(self):
        """Initialize Schwab client with error handling"""
        try:
            return easy_client(
                api_key=self.config.client_id,
                app_secret=self.config.client_secret,
                callback_url=self.config.callback_url,
                token_path=self.config.token_path,
                interactive=False,
            )
        except Exception as e:
            logger.error(f"Failed to initialize Schwab client: {e}")
            raise
    
    def _get_account_hash(self) -> str:
        """Get account hash with error handling"""
        try:
            accounts = self.client.get_account_numbers().json()
            if not accounts:
                raise ValueError("No accounts found")
            return accounts[0]['hashValue']
        except Exception as e:
            logger.error(f"Failed to get account hash: {e}")
            raise
    
    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        try:
            resp = self.client.get_account(
                self.account_hash,
                fields=[Client.Account.Fields.POSITIONS]
            ).json()
            return resp.get("securitiesAccount", {}).get("positions", [])
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_open_orders(self) -> List[Dict]:
        """Get open orders with normalization"""
        try:
            raw_orders = self.client.get_orders_for_account(self.account_hash).json()
            orders_list = raw_orders if isinstance(raw_orders, list) else raw_orders.get("data", raw_orders)
            
            if self.config.debug:
                logger.debug(f"Raw orders count: {len(orders_list)}")
                for o in orders_list:
                    logger.debug(f"Order {o.get('orderId')} status={o.get('status')} remaining={o.get('remainingQuantity')}")
            
            open_orders = [o for o in orders_list if o.get("remainingQuantity", 0) > 0]
            
            if self.config.debug:
                logger.debug(f"Open orders count: {len(open_orders)}")
            
            return open_orders
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []
    
    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get historical market data for a symbol"""
        try:
            start = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")) - timedelta(days=35)
            hist = self.client.get_price_history_every_day(symbol, start_datetime=start).json()
            candles = hist.get('candles', [])
            
            if not candles:
                logger.warning(f"No market data found for {symbol}")
                return None
            
            # Validate we have enough data for calculations
            min_required = max(self.config.sma_period, self.config.ema_period, 
                             self.config.atr_period + 1, self.config.chandelier_period)
            
            if len(candles) < min_required:
                logger.warning(f"Insufficient data for {symbol}. Need {min_required}, got {len(candles)}")
                return None
            
            return MarketData(
                symbol=symbol,
                highs=[c['high'] for c in candles],
                lows=[c['low'] for c in candles],
                closes=[c['close'] for c in candles]
            )
        except Exception as e:
            logger.error(f"Failed to get market data for {symbol}: {e}")
            return None
    
    def get_position_quantity(self, symbol: str, positions: List[Dict]) -> float:
        """Get position quantity for a symbol"""
        pos = next((p for p in positions if p['instrument']['assetType'] != "COLLECTIVE_INVESTMENT" 
                    and p['instrument']['symbol'] == symbol), None)
        return (pos.get('longQuantity', 0) - pos.get('shortQuantity', 0)) if pos else 0
    
    def get_position_info(self, symbol: str, positions: List[Dict]) -> Tuple[float, Optional[float]]:
        """Get position quantity and average cost"""
        pos = next((p for p in positions if p['instrument']['assetType'] != "COLLECTIVE_INVESTMENT" 
                    and p['instrument']['symbol'] == symbol), None)
        
        if not pos:
            return 0, None
        
        quantity = pos.get('longQuantity', 0) - pos.get('shortQuantity', 0)
        avg_cost = pos.get('averagePrice', None)
        
        # Log position details for debugging
        if self.config.debug and quantity > 0:
            logger.debug(f"{symbol}: Position quantity={quantity}, avg_cost={avg_cost}")
        
        return quantity, avg_cost
    
    def find_existing_sell_order(self, symbol: str, open_orders: List[Dict]) -> Optional[Dict]:
        """Find existing sell order for a symbol"""
        return next(
            (o for o in open_orders
             if any(leg['instrument']['symbol'] == symbol and leg['instruction'] == 'SELL'
                    for leg in o['orderLegCollection'])),
            None
        )
    
    def calculate_exit_price(self, market_data: MarketData, current_price: float = None, 
                           avg_cost: float = None) -> Tuple[float, float, float, str]:
        """Calculate adaptive exit price based on position P&L"""
        try:
            # Calculate base indicators
            ema = TechnicalIndicators.exponential_moving_average(
                market_data.closes, self.config.ema_period)
            chandelier = TechnicalIndicators.chandelier_exit(
                market_data, self.config.chandelier_period, self.config.chandelier_multiplier)
            
            # Use latest close if current_price not provided
            if current_price is None:
                current_price = market_data.closes[-1]
            
            # Adaptive logic based on position P&L
            if avg_cost is not None:
                unrealized_pnl_pct = (current_price - avg_cost) / avg_cost
                
                if unrealized_pnl_pct >= self.config.profit_threshold:
                    # Winning trade - use aggressive trailing stop (lower of the two)
                    exit_price = min(ema, chandelier)
                    strategy = "WINNER_TRAILING"
                    logger.debug(f"{market_data.symbol}: Using WINNER_TRAILING strategy. "
                               f"P&L: {unrealized_pnl_pct:.1%}, Stop: min({ema:.2f}, {chandelier:.2f}) = {exit_price:.2f}")
                    
                elif unrealized_pnl_pct <= self.config.loss_threshold:
                    # Losing trade - cut losses early with tight stop
                    tight_stop = avg_cost * (1 - self.config.max_loss_percent)  # Max loss protection
                    conservative_stop = min(ema, chandelier)  # More aggressive of the two indicators
                    exit_price = max(conservative_stop, tight_stop)
                    strategy = "LOSS_CUTTING"
                    logger.debug(f"{market_data.symbol}: Using LOSS_CUTTING strategy. "
                               f"P&L: {unrealized_pnl_pct:.1%}, Stop: max({conservative_stop:.2f}, {tight_stop:.2f}) = {exit_price:.2f}")
                    
                else:
                    # Break-even zone - use conservative approach
                    exit_price = max(ema, chandelier)
                    strategy = "BREAKEVEN_CONSERVATIVE"
                    logger.debug(f"{market_data.symbol}: Using BREAKEVEN_CONSERVATIVE strategy. "
                               f"P&L: {unrealized_pnl_pct:.1%}, Stop: max({ema:.2f}, {chandelier:.2f}) = {exit_price:.2f}")
            else:
                # Fallback to original logic if no cost basis available
                exit_price = max(ema, chandelier)
                strategy = "DEFAULT_CONSERVATIVE"
                logger.debug(f"{market_data.symbol}: Using DEFAULT_CONSERVATIVE strategy (no cost basis). "
                           f"Stop: max({ema:.2f}, {chandelier:.2f}) = {exit_price:.2f}")
            
            return exit_price, ema, chandelier, strategy
            
        except Exception as e:
            logger.error(f"Failed to calculate exit price for {market_data.symbol}: {e}")
            raise
    
    def create_stop_order(self, symbol: str, quantity: float, stop_price: float) -> Dict:
        """Create stop order specification"""
        stop_str = f"{stop_price:.2f}"
        return (
            equity_sell_limit(symbol, quantity, stop_str)
            .set_order_type(OrderType.STOP)
            .clear_price()
            .set_stop_price(stop_str)
            .set_duration(Duration.GOOD_TILL_CANCEL)
            .build()
        )
    
    def execute_order_action(self, symbol: str, quantity: float, exit_price: float, 
                           ema: float, chandelier: float, existing_order: Optional[Dict], 
                           strategy: str = "DEFAULT") -> bool:
        """Execute order placement or replacement"""
        spec = self.create_stop_order(symbol, quantity, exit_price)
        
        if existing_order:
            action = f"Replace order for {symbol}. {existing_order['orderId']} ➔ STOP @ {exit_price:.2f}. " \
                    f"Strategy={strategy}, EMA10={ema:.2f}, chandelier_exit={chandelier:.2f}"
        else:
            action = f"Place new STOP sell order for {symbol} x{quantity} @ {exit_price:.2f}. " \
                    f"Strategy={strategy}, EMA10={ema:.2f}, chandelier_exit={chandelier:.2f}"
        
        if self.config.dry_run:
            logger.info(f"[DRY RUN] {action}")
            return True
        
        try:
            if existing_order:
                resp = self.client.replace_order(self.account_hash, existing_order['orderId'], spec)
                logger.info(f"REPLACE_ORDER RESPONSE: {resp.status_code} - {resp.text}")
                logger.info(f"Replaced order for {symbol} at stop price {exit_price:.2f}. "
                           f"Strategy={strategy}, EMA10={ema:.2f}, chandelier_exit={chandelier:.2f}")
            else:
                resp = self.client.place_order(self.account_hash, spec)
                logger.info(f"PLACE_ORDER RESPONSE: {resp.status_code} - {resp.text}")
                logger.info(f"Placed new stop order for {symbol} at stop price {exit_price:.2f}. "
                           f"Strategy={strategy}, EMA10={ema:.2f}, chandelier_exit={chandelier:.2f}")
            
            return resp.status_code < 400
        except Exception as e:
            logger.error(f"Error {'replacing' if existing_order else 'placing'} order for {symbol}: {e}")
            return False
    
    def process_symbol(self, symbol: str, positions: List[Dict], open_orders: List[Dict]) -> bool:
        """Process trading logic for a single symbol"""
        logger.info(f"Processing symbol: {symbol}")
        
        # Get position info including cost basis
        quantity, avg_cost = self.get_position_info(symbol, positions)
        if quantity <= 0:
            logger.info(f"{symbol}: no shares owned, skipping.")
            return True
        
        # Get market data
        market_data = self.get_market_data(symbol)
        if not market_data:
            logger.error(f"Could not get market data for {symbol}")
            return False
        
        # Find existing order
        existing_order = self.find_existing_sell_order(symbol, open_orders)
        
        # Calculate adaptive exit price
        try:
            current_price = market_data.closes[-1]
            exit_price, ema, chandelier, strategy = self.calculate_exit_price(
                market_data, current_price, avg_cost)
            
            # Log the strategy being used and P&L info
            if avg_cost:
                pnl_pct = (current_price - avg_cost) / avg_cost
                unrealized_pnl = (current_price - avg_cost) * quantity
                logger.info(f"{symbol}: Strategy={strategy}, P&L={pnl_pct:.1%} (${unrealized_pnl:.2f}), "
                           f"Current=${current_price:.2f}, Avg_Cost=${avg_cost:.2f}, "
                           f"Stop=${exit_price:.2f}")
            else:
                logger.info(f"{symbol}: Strategy={strategy}, Current=${current_price:.2f}, Stop=${exit_price:.2f}")
        
        except Exception as e:
            logger.error(f"Failed to calculate exit price for {symbol}: {e}")
            return False
        
        # Execute order action with strategy info
        return self.execute_order_action(symbol, quantity, exit_price, ema, chandelier, existing_order, strategy)
    
    def run(self) -> bool:
        """Main execution method"""
        logger.info("Starting trading manager")
        
        try:
            # Get positions and orders
            positions = self.get_positions()
            open_orders = self.get_open_orders()
            
            success_count = 0
            for symbol in self.config.tickers:
                if self.process_symbol(symbol, positions, open_orders):
                    success_count += 1
                else:
                    logger.error(f"Failed to process {symbol}")
            
            logger.info(f"Successfully processed {success_count}/{len(self.config.tickers)} symbols")
            return success_count == len(self.config.tickers)
            
        except Exception as e:
            logger.error(f"Fatal error in trading manager: {e}")
            return False

def main():
    """Main entry point"""
    try:
        # Validate environment first
        if not validate_environment():
            exit(1)
        
        config = load_trading_config()
        if config.debug:
            logging.getLogger().setLevel(logging.DEBUG)
        
        manager = TradingManager(config)
        success = manager.run()
        
        if not success:
            logger.error("Trading run completed with errors")
            exit(1)
        else:
            logger.info("Trading run completed successfully")
            
    except Exception as e:
        logger.error(f"Application failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()