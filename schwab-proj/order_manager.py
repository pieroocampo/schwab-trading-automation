from schwab.auth import easy_client
from schwab.client import Client
from schwab.orders.common import OrderType, Duration
from schwab.orders.equities import equity_sell_limit
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# === CONFIG ===
load_dotenv()  # reads .env into os.environ
CLIENT_ID     = os.getenv("SCHWAB_CLIENT_ID")
CLIENT_SECRET = os.getenv("SCHWAB_CLIENT_SECRET")

CALLBACK_URL  = 'https://127.0.0.1'
TOKEN_PATH    = 'token.json'
TICKERS       = ['DDD', 'NFLX', 'ASC']
dry_run       = True   # <-- Set to False to actually submit

# === CLIENT SETUP ===
client = easy_client(
    api_key=CLIENT_ID,
    app_secret=CLIENT_SECRET,
    callback_url=CALLBACK_URL,
    token_path=TOKEN_PATH
)
accounts     = client.get_account_numbers().json()
acct_hash    = accounts[0]['hashValue']
positions    = client.get_account(acct_hash, fields=[Client.Account.Fields.POSITIONS]).json().get('positions', [])
open_orders  = client.get_orders_for_account(acct_hash, status='OPEN').json()

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
    closes = [d['closePrice'] for d in hist if 'closePrice' in d][-20:]
    mavg20 = sum(closes)/len(closes)

    # 4) Build STOP market @ MA, GTC
    spec = (
        equity_sell_limit(symbol, qty, mavg20)
        .set_order_type(OrderType.STOP)
        .clear_price()
        .set_stop_price(mavg20)
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
            client.replace_order(existing['orderId'], acct_hash, spec)
            print(f"Replaced order {existing['orderId']} for {symbol}")
        else:
            client.place_order(acct_hash, spec)
            print(f"Placed new stop order for {symbol}")