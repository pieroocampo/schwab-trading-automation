import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json

from schwab.auth import easy_client
from databricks.sdk import WorkspaceClient

from config import load_export_config, setup_logging, load_logging_config, validate_environment

# Initialize logging
logging_config = load_logging_config()
logger = setup_logging(logging_config, 'order_export.log')

class DatabricksManager:
    """Manages Databricks operations"""
    
    def __init__(self, config):
        self.config = config
        self._client = None
    
    @property
    def client(self) -> WorkspaceClient:
        """Lazy initialization of Databricks client"""
        if self._client is None:
            try:
                self._client = WorkspaceClient(profile=self.config.databricks_profile)
            except Exception as e:
                logger.error(f"Failed to initialize Databricks client: {e}")
                raise
        return self._client
    
    def upload_file(self, local_file_path: str, remote_path: str) -> bool:
        """Upload file to Databricks with error handling"""
        try:
            if not Path(local_file_path).exists():
                logger.error(f"Local file not found: {local_file_path}")
                return False
            
            with open(local_file_path, "rb") as input_stream:
                self.client.files.upload(remote_path, input_stream, overwrite=True)
            
            logger.info(f"Successfully uploaded {local_file_path} to {remote_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload file to Databricks: {e}")
            return False
    
    def trigger_job(self, job_id: int) -> bool:
        """Trigger Databricks job with error handling"""
        try:
            run_response = self.client.jobs.run_now(job_id)
            logger.info(f"Successfully triggered Databricks job {job_id}, run ID: {run_response.run_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to trigger Databricks job {job_id}: {e}")
            return False

class OrderExporter:
    """Manages order export operations"""
    
    def __init__(self, config):
        self.config = config
        self.client = self._initialize_client()
        self.account_hash = self._get_account_hash()
        self.execution_state_file = "last_execution.json"
    
    def _initialize_client(self):
        """Initialize Schwab client with error handling"""
        try:
            return easy_client(
                api_key=self.config.client_id,
                app_secret=self.config.client_secret,
                callback_url=self.config.callback_url,
                token_path=self.config.token_path,
                enforce_enums=False
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
            return accounts[0]["hashValue"]
        except Exception as e:
            logger.error(f"Failed to get account hash: {e}")
            raise
    
    def _load_last_execution_date(self) -> Optional[datetime]:
        """Load the last execution date from state file"""
        try:
            if Path(self.execution_state_file).exists():
                with open(self.execution_state_file, 'r') as f:
                    state = json.load(f)
                    last_date = state.get('last_execution_date')
                    if last_date:
                        return datetime.fromisoformat(last_date)
        except Exception as e:
            logger.warning(f"Failed to load last execution date: {e}")
        return None
    
    def _save_execution_date(self, execution_date: datetime) -> bool:
        """Save the current execution date to state file"""
        try:
            from datetime import timezone
            state = {
                'last_execution_date': execution_date.isoformat(),
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            with open(self.execution_state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Saved execution date: {execution_date.isoformat()}")
            return True
        except Exception as e:
            logger.error(f"Failed to save execution date: {e}")
            return False
    
    def _get_date_range(self) -> tuple[datetime, datetime]:
        """Get the date range for order extraction"""
        from datetime import timezone
        
        # Current execution time with timezone awareness
        to_date = datetime.now(timezone.utc)
        
        # Load last execution date
        last_execution = self._load_last_execution_date()
        
        if last_execution:
            from_date = last_execution
            # Ensure timezone consistency - all dates should be UTC
            if from_date.tzinfo is None:
                from_date = from_date.replace(tzinfo=timezone.utc)
            logger.info(f"Using incremental extraction from {from_date.isoformat()} to {to_date.isoformat()}")
        else:
            # First run - use cutoff date from config but respect 60-day API limit
            config_cutoff = datetime.fromisoformat(self.config.cutoff_date)
            # Ensure config cutoff is timezone-aware
            if config_cutoff.tzinfo is None:
                config_cutoff = config_cutoff.replace(tzinfo=timezone.utc)
            
            sixty_days_ago = to_date - timedelta(days=60)
            from_date = max(config_cutoff, sixty_days_ago)
            logger.info(f"First run - extracting from {from_date.isoformat()} to {to_date.isoformat()}")
        
        return from_date, to_date
    
    def get_all_orders(self) -> List[Dict]:
        """Fetch orders from account using incremental date range"""
        try:
            # Get date range for this execution
            from_date, to_date = self._get_date_range()
            
            # API call with date range
            resp = self.client.get_orders_for_account(
                self.account_hash,
                from_entered_datetime=from_date,
                to_entered_datetime=to_date
            )
            logger.debug(f"Orders API response status: {resp.status_code}")
            
            if resp.status_code != 200:
                logger.error(f"Failed to fetch orders: HTTP {resp.status_code}")
                return []
            
            raw = resp.json()
            orders_list = raw if isinstance(raw, list) else raw.get("data", raw.get("orders", []))
            
            logger.info(f"Retrieved {len(orders_list)} total orders")
            return orders_list
            
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    def filter_filled_orders(self, orders: List[Dict]) -> List[Dict]:
        """Filter orders for filled status only - date filtering already handled by API"""
        try:
            filled_orders = []
            total_orders = len(orders)
            status_counts = {}
            
            for order in orders:
                status = order.get("status", "UNKNOWN")
                status_counts[status] = status_counts.get(status, 0) + 1
                
                if status != "FILLED":
                    continue
                
                # Validate that the order has an enteredTime (for logging purposes)
                entered_time_str = order.get("enteredTime", "")
                if not entered_time_str:
                    logger.warning(f"Order {order.get('orderId')} missing enteredTime")
                    continue
                
                filled_orders.append(order)
            
            # Log status breakdown for debugging
            status_summary = ", ".join([f"{status}: {count}" for status, count in status_counts.items()])
            logger.info(f"Order status breakdown from {total_orders} total orders: {status_summary}")
            logger.info(f"Found {len(filled_orders)} filled orders")
            return filled_orders
            
        except Exception as e:
            logger.error(f"Failed to filter orders: {e}")
            return []
    
    def write_orders_to_csv(self, orders: List[Dict]) -> bool:
        """Write orders to CSV file"""
        try:
            with open(self.config.output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["orderId", "symbol", "instruction", "quantity", "price", "time"])
                
                total_rows = 0
                for order in orders:
                    try:
                        # Extract order leg information
                        order_legs = order.get("orderLegCollection", [])
                        if not order_legs:
                            logger.warning(f"Order {order.get('orderId')} has no order legs")
                            continue
                        
                        leg_info = order_legs[0]
                        symbol = leg_info.get("instrument", {}).get("symbol", "UNKNOWN")
                        instruction = leg_info.get("instruction", "UNKNOWN")
                        
                        # Write execution legs
                        for activity in order.get("orderActivityCollection", []):
                            if activity.get("activityType") == "EXECUTION":
                                for leg in activity.get("executionLegs", []):
                                    writer.writerow([
                                        order.get("orderId"),
                                        symbol,
                                        instruction,
                                        leg.get("quantity"),
                                        leg.get("price"),
                                        leg.get("time")
                                    ])
                                    total_rows += 1
                    
                    except Exception as e:
                        logger.error(f"Failed to process order {order.get('orderId')}: {e}")
                        continue
                
                logger.info(f"Wrote {total_rows} execution legs to {self.config.output_file}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to write CSV file: {e}")
            return False
    
    def export_orders(self) -> bool:
        """Main export process"""
        logger.info("Starting order export process")
        
        # Get date range for this execution
        from_date, to_date = self._get_date_range()
        
        # Get all orders
        all_orders = self.get_all_orders()
        if not all_orders:
            logger.warning("No orders retrieved for the specified date range")
            # Save execution end time to ensure no gaps in next run
            from datetime import timezone
            self._save_execution_date(datetime.now(timezone.utc))
            return True
        
        # Filter for filled orders (date filtering already handled by API)
        filled_orders = self.filter_filled_orders(all_orders)
        if not filled_orders:
            logger.warning("No filled orders found matching criteria")
            # Save execution end time to ensure no gaps in next run  
            from datetime import timezone
            self._save_execution_date(datetime.now(timezone.utc))
            return True
        
        # Write to CSV
        success = self.write_orders_to_csv(filled_orders)
        
        # Save execution date only if write was successful
        # Use current time to ensure we don't miss any orders in next run
        if success:
            from datetime import timezone
            self._save_execution_date(datetime.now(timezone.utc))
        
        return success

class OrderExportManager:
    """Main manager for the complete export and upload process"""
    
    def __init__(self, config):
        self.config = config
        self.exporter = OrderExporter(config)
        self.databricks = DatabricksManager(config)
    
    def _has_orders_to_upload(self) -> bool:
        """Check if CSV file exists and has order data (more than just header)"""
        try:
            if not Path(self.config.output_file).exists():
                return False
            
            with open(self.config.output_file, 'r') as f:
                lines = f.readlines()
                # File should have header + at least one data row
                return len(lines) > 1
                
        except Exception as e:
            logger.warning(f"Failed to check CSV file content: {e}")
            return False
    
    def _delete_uploaded_file(self) -> bool:
        """Delete the CSV file after successful upload to prevent duplicate uploads"""
        try:
            file_path = Path(self.config.output_file)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted {self.config.output_file} after successful upload")
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete {self.config.output_file}: {e}")
            return False
    
    def run(self) -> bool:
        """Execute the complete export process"""
        logger.info("Starting order export and upload process")
        
        try:
            # Export orders to CSV
            if not self.exporter.export_orders():
                logger.error("Failed to export orders")
                return False
            
            # Check if we have orders to upload
            if not self._has_orders_to_upload():
                logger.info("No orders found in export - skipping Databricks upload and job trigger")
                logger.info("Export process completed successfully (no new data)")
                return True
            
            logger.info(f"Orders found in {self.config.output_file} - proceeding with Databricks operations")
            
            # Upload to Databricks
            if not self.databricks.upload_file(
                self.config.output_file, 
                self.config.databricks_remote_path
            ):
                logger.error("Failed to upload to Databricks")
                return False
            
            # Trigger Databricks job
            if not self.databricks.trigger_job(self.config.databricks_job_id):
                logger.error("Failed to trigger Databricks job")
                return False
            
            logger.info("Order export and upload completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Fatal error in export process: {e}")
            return False

def main():
    """Main entry point"""
    try:
        # Validate environment first
        if not validate_environment():
            exit(1)
        
        config = load_export_config()
        manager = OrderExportManager(config)
        
        success = manager.run()
        
        if not success:
            logger.error("Export process completed with errors")
            exit(1)
        else:
            logger.info("Export process completed successfully")
            
    except Exception as e:
        logger.error(f"Application failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()