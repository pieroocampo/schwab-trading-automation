"""
Centralized configuration management for Schwab Trading Automation

This module provides shared configuration classes and utilities for both
order management and order export functionalities.
"""

import os
import logging
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv


@dataclass
class SchwabAPIConfig:
    """Base configuration for Schwab API access"""
    client_id: str
    client_secret: str
    callback_url: str
    token_path: str = 'token.json'
    
    def __post_init__(self):
        # Validate required fields
        if not self.client_id:
            raise ValueError("SCHWAB_CLIENT_ID is required")
        if not self.client_secret:
            raise ValueError("SCHWAB_CLIENT_SECRET is required")
        if not self.callback_url:
            raise ValueError("CALLBACK_URL is required")


@dataclass
class TradingConfig(SchwabAPIConfig):
    """Configuration for trading operations"""
    # Trading parameters
    tickers: List[str] = None
    dry_run: bool = False
    debug: bool = False
    
    # Technical indicator parameters
    sma_period: int = 20
    ema_period: int = 10
    breakeven_ema_period: int = 5  # EMA period for breakeven stops (using lows)
    atr_period: int = 14
    chandelier_period: int = 22
    chandelier_multiplier: float = 3.0
    
    # Risk management parameters
    max_position_size: float = 10000.0  # Maximum position size in dollars
    max_daily_trades: int = 10
    min_price: float = 1.0  # Minimum stock price to trade
    
    # Adaptive stop parameters
    profit_threshold: float = 0.05  # 5% profit to switch to aggressive trailing
    loss_threshold: float = -0.03   # 3% loss to tighten stops
    max_loss_percent: float = 0.05  # 5% maximum loss per position
    breakeven_buffer: float = 0.01  # 1% buffer around breakeven
    
    def __post_init__(self):
        super().__post_init__()
        if self.tickers is None:
            self.tickers = []
        
        # Validate technical indicator periods
        if self.sma_period <= 0:
            raise ValueError("SMA period must be positive")
        if self.ema_period <= 0:
            raise ValueError("EMA period must be positive")
        if self.breakeven_ema_period <= 0:
            raise ValueError("Breakeven EMA period must be positive")
        if self.atr_period <= 0:
            raise ValueError("ATR period must be positive")
        if self.chandelier_period <= 0:
            raise ValueError("Chandelier period must be positive")


@dataclass
class ExportConfig(SchwabAPIConfig):
    """Configuration for order export operations"""
    # File settings
    output_file: str = "filled_orders.csv"
    cutoff_date: str = "2025-08-16T00:00:00+00:00"  # Within Schwab API 60-day limit
    
    # Databricks settings
    databricks_profile: str = "mypharos"
    databricks_remote_path: str = "/Volumes/workspace/default/landing/filled_orders.csv"
    databricks_job_id: int = 939121727711316
    
    # Export settings
    include_cancelled: bool = False
    max_orders_per_file: int = 10000


@dataclass
class LoggingConfig:
    """Configuration for logging settings"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    file_enabled: bool = True
    console_enabled: bool = True
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


def setup_logging(config: LoggingConfig, log_filename: str) -> logging.Logger:
    """Set up logging with the given configuration"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    formatter = logging.Formatter(config.format)
    
    if config.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    if config.file_enabled:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_filename,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def load_trading_config() -> TradingConfig:
    """Load trading configuration from environment variables"""
    load_dotenv()
    
    # Parse tickers from comma-separated string
    tickers_str = os.getenv("TICKERS")
    tickers = [ticker.strip() for ticker in tickers_str.split(",") if ticker.strip()]
    
    return TradingConfig(
        client_id=os.getenv("SCHWAB_CLIENT_ID"),
        client_secret=os.getenv("SCHWAB_CLIENT_SECRET"),
        callback_url=os.getenv("CALLBACK_URL"),
        token_path=os.getenv("TOKEN_PATH", "token.json"),
        tickers=tickers,
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        debug=os.getenv("DEBUG", "false").lower() == "true",
        
        # Technical indicators
        sma_period=int(os.getenv("SMA_PERIOD", "20")),
        ema_period=int(os.getenv("EMA_PERIOD", "10")),
        breakeven_ema_period=int(os.getenv("BREAKEVEN_EMA_PERIOD", "5")),
        atr_period=int(os.getenv("ATR_PERIOD", "14")),
        chandelier_period=int(os.getenv("CHANDELIER_PERIOD", "22")),
        chandelier_multiplier=float(os.getenv("CHANDELIER_MULTIPLIER", "3.0")),
        
        # Risk management
        max_position_size=float(os.getenv("MAX_POSITION_SIZE", "10000.0")),
        max_daily_trades=int(os.getenv("MAX_DAILY_TRADES", "10")),
        min_price=float(os.getenv("MIN_PRICE", "1.0")),
        
        # Adaptive stop parameters
        profit_threshold=float(os.getenv("PROFIT_THRESHOLD", "0.05")),
        loss_threshold=float(os.getenv("LOSS_THRESHOLD", "-0.03")),
        max_loss_percent=float(os.getenv("MAX_LOSS_PERCENT", "0.05")),
        breakeven_buffer=float(os.getenv("BREAKEVEN_BUFFER", "0.01"))
    )


def load_export_config() -> ExportConfig:
    """Load export configuration from environment variables"""
    load_dotenv()
    
    return ExportConfig(
        client_id=os.getenv("SCHWAB_CLIENT_ID"),
        client_secret=os.getenv("SCHWAB_CLIENT_SECRET"),
        callback_url=os.getenv("CALLBACK_URL"),
        token_path=os.getenv("TOKEN_PATH", "token.json"),
        
        # Export settings
        output_file=os.getenv("OUTPUT_FILE", "filled_orders.csv"),
        cutoff_date=os.getenv("CUTOFF_DATE", "2024-06-15T00:00:00+00:00"),
        
        # Databricks settings
        databricks_profile=os.getenv("DATABRICKS_PROFILE", "mypharos"),
        databricks_remote_path=os.getenv("DATABRICKS_REMOTE_PATH", "/Volumes/workspace/default/landing/filled_orders.csv"),
        databricks_job_id=int(os.getenv("DATABRICKS_JOB_ID", "939121727711316")),
        
        # Export options
        include_cancelled=os.getenv("INCLUDE_CANCELLED", "false").lower() == "true",
        max_orders_per_file=int(os.getenv("MAX_ORDERS_PER_FILE", "10000"))
    )


def load_logging_config() -> LoggingConfig:
    """Load logging configuration from environment variables"""
    load_dotenv()
    
    return LoggingConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=os.getenv("LOG_FORMAT", "%(asctime)s - %(levelname)s - %(name)s - %(message)s"),
        file_enabled=os.getenv("LOG_FILE_ENABLED", "true").lower() == "true",
        console_enabled=os.getenv("LOG_CONSOLE_ENABLED", "true").lower() == "true",
        max_file_size=int(os.getenv("LOG_MAX_FILE_SIZE", str(10 * 1024 * 1024))),
        backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5"))
    )


# Environment validation
def validate_environment() -> bool:
    """Validate that all required environment variables are set"""
    load_dotenv()
    
    required_vars = [
        "SCHWAB_CLIENT_ID",
        "SCHWAB_CLIENT_SECRET", 
        "CALLBACK_URL"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file or environment settings.")
        return False
    
    return True
