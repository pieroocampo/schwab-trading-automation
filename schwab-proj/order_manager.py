from schwab.auth import easy_client, OAuth2Client
from schwab.client import Client
from schwab.orders.common import OrderType, Duration
from schwab.orders.equities import equity_sell_limit
from datetime import datetime, timedelta
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
import os

# === CONFIG ===
load_dotenv()  # reads .env into os.environ
CLIENT_ID     = os.getenv("SCHWAB_CLIENT_ID")
CLIENT_SECRET = os.getenv("SCHWAB_CLIENT_SECRET")

CALLBACK_URL  = os.getenv("CALLBACK_URL")
TOKEN_PATH    = 'token.json'
TICKERS       = ["NCLH", "EPAM", "WB", "TRMB", "VLO", "F", "VBTX", "ACHR","NVDA","VLO","DBRG", "ADBE", "DOUG", "NNBR", "STOK","IIF"]
dry_run       = False  # <-- Set to False to actually submit
debug         = False  # <-- Set to True to enable debug prints

# === CLIENT SETUP ===
client = easy_client(
    api_key=CLIENT_ID,
    app_secret=CLIENT_SECRET,
    callback_url=CALLBACK_URL,
    token_path=TOKEN_PATH
)
# ====================

accounts     = client.get_account_numbers().json()
acct_hash    = accounts[0]['hashValue']

resp = client.get_account(
    acct_hash,
    fields=[Client.Account.Fields.POSITIONS]
).json()

positions = resp.get("securitiesAccount", {}).get("positions", [])

raw_orders = client.get_orders_for_account(acct_hash).json()
# Normalize raw_orders into a list
orders_list = raw_orders if isinstance(raw_orders, list) else raw_orders.get("data", raw_orders)
if debug:
    print(f"DEBUG raw orders count: {len(orders_list)}")
    # Debug each order's status and remaining quantity
    for o in orders_list:
        print(f"DEBUG order {o.get('orderId')} status={o.get('status')} remaining={o.get('remainingQuantity')}")
# Consider an order open if it has any remaining quantity
open_orders = [o for o in orders_list if o.get("remainingQuantity", 0) > 0]
if debug:
    print(f"DEBUG open orders count: {len(open_orders)}")

for symbol in TICKERS:
    # 1) How many shares
    pos = next((p for p in positions if p['instrument']['symbol'] == symbol), None)
    qty = (pos.get('longQuantity', 0) - pos.get('shortQuantity', 0)) if pos else 0
    if qty <= 0:
        print(f"{symbol}: no shares owned, skipping.")
        continue

    # 2) Existing open SELL order?
    existing = next(
        (o for o in open_orders
         if any(leg['instrument']['symbol']==symbol and leg['instruction']=='SELL'
                for leg in o['orderLegCollection'])),
        None
    )

    # 3) Compute 20-day MA
    start = datetime.utcnow() - timedelta(days=30)
    hist  = client.get_price_history_every_day(symbol, start_datetime=start).json()
    candles = hist.get('candles', [])

    # unpack raw series
    highs   = [c['high']  for c in candles]
    lows    = [c['low']   for c in candles]
    closes  = [c['close'] for c in candles]

    # 1) 20-day SMA (for reference/filter)
    mavg20   = sum(closes[-20:]) / 20

    # 2) 10-day EMA (fast breakdown filter)
    ema_period = 10
    alpha      = 2 / (ema_period + 1)
    # seed EMA on the first of the window
    ema = closes[-ema_period]
    for price in closes[-ema_period+1:]:
        ema = alpha * price + (1 - alpha) * ema
    ema10 = ema

    # 3) ATR(14) – Average True Range
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1])
        )
        trs.append(tr)
    atr14 = sum(trs[-14:]) / 14

    # 4) Chandelier Exit (22-day high minus 3×ATR)
    highest_high    = max(highs[-22:])
    chandelier_exit = highest_high - 3 * atr14

    # 5) Choose your final stop: for example,
    #    - bail on a quick EMA break, or
    #    - give it room with the chandelier exit
    exit_price = max(ema10, chandelier_exit)

    # format as string (schwab-py deprecation warning fix)
    exit_str = f"{exit_price:.2f}"

    # --- then build your order spec using exit_str instead of mavg20_str ---
    spec = (
        equity_sell_limit(symbol, qty, exit_str)
        .set_order_type(OrderType.STOP)
        .clear_price()
        .set_stop_price(exit_str)
        .set_duration(Duration.GOOD_TILL_CANCEL)
        .build()
    )

    action = ""
    if existing:
        action = f"Replace order {existing['orderId']} ➔ STOP @ {exit_price:.2f}"
    else:
        action = f"Place new STOP sell order for {symbol} x{qty} @ {exit_price:.2f}"

    if dry_run:
        print(f"[DRY RUN] {action}")
    else:
        if existing:
            try:
                resp = client.replace_order(acct_hash, existing['orderId'], spec)
                print(f"REPLACE_ORDER RESPONSE: {resp.status_code} - {resp.text}")
                print(f"Replaced order for {symbol} at stop price {exit_str}")
            except Exception as e:
                print(f"Error replacing order for {symbol}: {e}")
        else:
            try:
                resp = client.place_order(acct_hash, spec)
                print(f"PLACE_ORDER RESPONSE: {resp.status_code} - {resp.text}")
                print(f"Placed new stop order for {symbol} at stop price {exit_str}")
            except Exception as e:
                print(f"Error placing order for {symbol}: {e}")