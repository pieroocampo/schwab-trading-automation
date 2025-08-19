#!/usr/bin/env python3
"""
Transform historical trades CSV to match Databricks upload schema.

This script processes history.csv and creates a new CSV with only Buy/Sell stock orders,
formatted to match the schema used in order_export.py for Databricks uploads.

Target schema: ["orderId", "symbol", "instruction", "quantity", "price", "time"]
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HistoryTransformer:
    """Transform historical trades to Databricks format"""
    
    def __init__(self, input_file: str = "history.csv", output_file: str = "historical_orders.csv"):
        self.input_file = input_file
        self.output_file = output_file
        
        # Valid actions for stock trades
        self.valid_actions = {"Buy", "Sell"}
        
        # Keywords to exclude (options, dividends, etc.)
        self.exclude_keywords = {
            "dividend", "option", "call", "put", "reorganized", "tender", "warrant",
            "rights", "spin", "merger", "split", "distribution", "interest"
        }
    
    def is_valid_stock_trade(self, row: Dict[str, str]) -> bool:
        """Check if row represents a valid stock Buy/Sell order"""
        
        # Must be Buy or Sell action
        action = row.get("Action", "").strip()
        if action not in self.valid_actions:
            return False
        
        # Must have a symbol
        symbol = row.get("Symbol", "").strip()
        if not symbol:
            return False
        
        # Must have quantity and price
        quantity = row.get("Quantity", "").strip()
        price = row.get("Price", "").strip()
        if not quantity or not price:
            return False
        
        # Check for options indicators in symbol (common patterns)
        if any(char in symbol for char in ["C", "P"]) and len(symbol) > 6:
            # Likely an option symbol (e.g., AAPL240119C00150000)
            return False
        
        # Check description for excluded keywords
        description = row.get("Description", "").lower()
        if any(keyword in description for keyword in self.exclude_keywords):
            return False
        
        return True
    
    def generate_order_id(self, row: Dict[str, str], row_index: int) -> str:
        """Generate a unique order ID for historical data"""
        # Create a hash from date + symbol + action + quantity + price + index
        data_string = f"{row['Date']}{row['Symbol']}{row['Action']}{row['Quantity']}{row['Price']}{row_index}"
        hash_object = hashlib.md5(data_string.encode())
        return f"HIST_{hash_object.hexdigest()[:12].upper()}"
    
    def clean_price(self, price_str: str) -> Optional[str]:
        """Clean price string (remove $ sign, handle empty values)"""
        if not price_str:
            return None
        
        # Remove $ sign and whitespace
        cleaned = price_str.replace("$", "").strip()
        
        # Validate it's a number
        try:
            float(cleaned)
            return cleaned
        except ValueError:
            logger.warning(f"Invalid price format: {price_str}")
            return None
    
    def format_date(self, date_str: str) -> Optional[str]:
        """Convert date from MM/DD/YYYY to ISO format"""
        try:
            # Parse date (assuming MM/DD/YYYY format)
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            # Return in ISO format with timezone (matching order_export.py format)
            return date_obj.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            logger.warning(f"Invalid date format: {date_str}")
            return None
    
    def clean_quantity(self, quantity_str: str) -> Optional[str]:
        """Clean quantity string and ensure it's positive"""
        if not quantity_str:
            return None
        
        try:
            # Remove any whitespace and convert to float to validate
            quantity = float(quantity_str.strip())
            # Return absolute value as string (some sells might have negative quantities)
            return str(abs(int(quantity)))
        except ValueError:
            logger.warning(f"Invalid quantity format: {quantity_str}")
            return None
    
    def transform_row(self, row: Dict[str, str], row_index: int) -> Optional[Dict[str, str]]:
        """Transform a single row to target format"""
        
        # Clean and validate all fields
        order_id = self.generate_order_id(row, row_index)
        symbol = row.get("Symbol", "").strip()
        instruction = row.get("Action", "").strip()  # Buy or Sell
        quantity = self.clean_quantity(row.get("Quantity", ""))
        price = self.clean_price(row.get("Price", ""))
        time = self.format_date(row.get("Date", ""))
        
        # Validate all required fields are present
        if not all([order_id, symbol, instruction, quantity, price, time]):
            logger.warning(f"Skipping row due to missing data: {row}")
            return None
        
        return {
            "orderId": order_id,
            "symbol": symbol,
            "instruction": instruction,
            "quantity": quantity,
            "price": price,
            "time": time
        }
    
    def transform(self) -> bool:
        """Main transformation process"""
        logger.info(f"Starting transformation of {self.input_file}")
        
        # Check if input file exists
        if not Path(self.input_file).exists():
            logger.error(f"Input file not found: {self.input_file}")
            return False
        
        try:
            transformed_rows = []
            total_rows = 0
            valid_trades = 0
            
            # Read and process input file
            with open(self.input_file, 'r', newline='', encoding='utf-8') as infile:
                reader = csv.DictReader(infile)
                
                for row_index, row in enumerate(reader, 1):
                    total_rows += 1
                    
                    # Check if this is a valid stock trade
                    if not self.is_valid_stock_trade(row):
                        continue
                    
                    # Transform the row
                    transformed_row = self.transform_row(row, row_index)
                    if transformed_row:
                        transformed_rows.append(transformed_row)
                        valid_trades += 1
            
            # Write output file
            if transformed_rows:
                with open(self.output_file, 'w', newline='', encoding='utf-8') as outfile:
                    fieldnames = ["orderId", "symbol", "instruction", "quantity", "price", "time"]
                    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(transformed_rows)
                
                logger.info(f"✅ Transformation completed successfully!")
                logger.info(f"📊 Total rows processed: {total_rows}")
                logger.info(f"📈 Valid stock trades found: {valid_trades}")
                logger.info(f"💾 Output saved to: {self.output_file}")
                
                # Show sample of first few records
                logger.info("📋 Sample of transformed data:")
                for i, row in enumerate(transformed_rows[:3]):
                    logger.info(f"   {i+1}. {row['instruction']} {row['quantity']} {row['symbol']} @ ${row['price']} on {row['time'][:10]}")
                
                return True
            else:
                logger.warning("No valid stock trades found in the input file")
                return False
                
        except Exception as e:
            logger.error(f"Error during transformation: {e}")
            return False

def main():
    """Main entry point"""
    transformer = HistoryTransformer()
    
    success = transformer.transform()
    
    if success:
        logger.info("🎉 Historical data transformation completed successfully!")
    else:
        logger.error("❌ Transformation failed")
        exit(1)

if __name__ == "__main__":
    main()
