import os, csv, json
from schwab.auth import easy_client
from dotenv import load_dotenv
from datetime import datetime
from databricks.sdk import WorkspaceClient

def upload_export_to_databricks():
    """
    Uploads the filled_orders.csv file to Databricks.
    This function is a placeholder and should be implemented based on your Databricks setup.
    """
    w = WorkspaceClient(profile="mypharos")
    remote_path = "/Volumes/workspace/default/landing/filled_orders.csv"
    with open("filled_orders.csv", "rb") as input_stream:
        w.files.upload(remote_path, input_stream, overwrite=True)

def trigger_databricks_job():
    """
    Triggers a Databricks job to process the uploaded CSV file.
    This function is a placeholder and should be implemented based on your Databricks job setup.
    """
    w = WorkspaceClient(profile="mypharos")
    job_id = 939121727711316
    w.jobs.run_now(job_id)

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

# 4) normalize into a list
orders_list = raw if isinstance(raw, list) else raw.get("data", raw.get("orders", []))

 # Only include orders entered on or after April 1, 2025
cutoff = datetime.fromisoformat("2025-04-01T00:00:00+00:00")

# 5) filter for filled orders
filled = []
for o in orders_list:
    if o.get("status") != "FILLED":
        continue
    # parse enteredTime (convert +0000 to +00:00 for fromisoformat)
    entered = datetime.fromisoformat(o["enteredTime"].replace("+0000", "+00:00"))
    if entered >= cutoff:
        filled.append(o)
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

upload_export_to_databricks()
trigger_databricks_job()

print("Uploaded filled_orders.csv to Databricks and triggered job.")