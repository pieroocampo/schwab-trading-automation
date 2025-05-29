import os, csv, json
from schwab.auth import easy_client
from dotenv import load_dotenv

load_dotenv()
client = easy_client(
    api_key=os.getenv("SCHWAB_CLIENT_ID"),
    app_secret=os.getenv("SCHWAB_CLIENT_SECRET"),
    callback_url=os.getenv("CALLBACK_URL"),
    token_path="token.json",
    enforce_enums=False
)

# 1) fetch your account hash
acct_hash = client.get_account_numbers().json()[0]["hashValue"]

# 2) pull *all* orders via the library
resp = client.get_orders_for_account(acct_hash)
print("DEBUG HTTP", resp.status_code)
raw = resp.json()

# 3) dump the structure so you can inspect exactly where 'FILLED' lives
print(json.dumps(raw, indent=2))  
# ↳ run this, look in your console for where the orders array is,
#    then note whether it's raw["data"], raw["orders"], or raw itself.

# 4) normalize into a list
orders_list = raw if isinstance(raw, list) else raw.get("data", raw.get("orders", []))

# 5) filter for filled orders
filled = [o for o in orders_list if o.get("status") == "FILLED"]
print(f"DEBUG found {len(filled)} FILLED orders")

# 6) write CSV of each execution leg, including instruction column
with open("filled_orders.csv", "w", newline="") as f:
    w = csv.writer(f)
    # include instruction column
    w.writerow(["orderId", "symbol", "instruction", "quantity", "price", "time"])
    for o in filled:
        # extract symbol and instruction from orderLegCollection
        leg_info    = o["orderLegCollection"][0]
        sym         = leg_info["instrument"]["symbol"]
        instruction = leg_info.get("instruction", "UNKNOWN")
        # write each execution leg
        for act in o.get("orderActivityCollection", []):
            if act.get("activityType") == "EXECUTION":
                for leg in act.get("executionLegs", []):
                    w.writerow([
                        o.get("orderId"),
                        sym,
                        instruction,
                        leg.get("quantity"),
                        leg.get("price"),
                        leg.get("time")
                    ])

print(f"Wrote {len(filled)} orders to filled_orders.csv")