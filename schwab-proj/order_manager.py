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

#AUTH_URL      = "https://api.schwabapi.com/v1/oauth/authorize"
#TOKEN_URL     = "https://api.schwabapi.com/v1/oauth/token"

CALLBACK_URL  = os.getenv("CALLBACK_URL")
TOKEN_PATH    = 'token.json'
TICKERS       = ["NCLH", "EPAM", "WB", "TRMB", "VLO", "F", "VBTX", "ACHR"]
dry_run       = False   # <-- Set to False to actually submit

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

open_orders_response = client.get_orders_for_account(acct_hash).json()
open_orders = [order for order in open_orders_response if order.get("status") == "OPEN" or order.get("status") == "AWAITING_STOP_CONDITION"]

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
    closes = closes = [c['close'] for c in hist.get('candles', [])][-20:]
    mavg20 = sum(closes)/len(closes)
    mavg20_str = f"{mavg20:.2f}"

    # 4) Build STOP market @ MA, GTC
    spec = (
        equity_sell_limit(symbol, qty, mavg20_str)
        .set_order_type(OrderType.STOP)
        .clear_price()
        .set_stop_price(mavg20_str)
        .set_duration(Duration.GOOD_TILL_CANCEL)
        .build()
    )

    action = ""
    if existing:
        action = f"Replace order {existing['orderId']} ➔ STOP @ {mavg20:.2f}"
    else:
        action = f"Place new STOP sell order for {symbol} x{qty} @ {mavg20:.2f}"

    if dry_run:
        print(f"[DRY RUN] {action}")
    else:
        if existing:
            order_resp = client.replace_order(acct_hash, existing['orderId'], spec)
            print(f"Replaced order {existing['orderId']} for {symbol}")
        else:
            client.place_order(acct_hash, spec)
            print(f"Placed new stop order for {symbol}")