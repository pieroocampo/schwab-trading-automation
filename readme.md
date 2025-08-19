# Schwab Trading Automation

A comprehensive Python project for automating Schwab trading operations, including order management, data export, and Databricks integration. This project provides both automated trading capabilities and efficient data pipeline functionality.

## 🚀 Features

### Trading Automation (`order_manager.py`)
- **OAuth2 Authentication** with Schwab API
- **Portfolio Management**: Retrieve account positions and open orders
- **Technical Indicators**:
  - 20-day Simple Moving Average (SMA)
  - 10-day Exponential Moving Average (EMA)
  - 14-day Average True Range (ATR)
  - Chandelier Exit stop calculations
- **Automated Stop-Loss Management**: Place/replace orders based on technical analysis
- **Dry-Run Mode**: Test strategies without executing trades

### Order Export & Data Pipeline (`order_export.py`)
- **Incremental Data Export**: Tracks last execution date for efficient extraction
- **Schwab API Integration**: Export filled orders with proper date range handling
- **Databricks Integration**: Automatic file upload and job triggering
- **Smart Skipping**: Skip uploads when no new orders found
- **CSV Export**: Clean, structured data format
- **Robust Error Handling**: Comprehensive logging and retry logic

### Historical Data Processing (`transform_history.py`)
- **CSV Transformation**: Convert historical trading data to standardized format
- **Smart Filtering**: Exclude dividends, options, and reorganized issues
- **Data Validation**: Clean prices, quantities, and dates
- **Schema Matching**: Output matches Databricks upload format

## 📋 Requirements

- **Python 3.9+** (required for zoneinfo module)
- **Schwab API credentials** (Client ID, Secret, Callback URL)
- **Databricks workspace** (optional, for data pipeline features)

### Core Dependencies
- `schwab-py>=1.5.0` - Schwab API client
- `databricks-sdk>=0.43.0` - Databricks integration  
- `python-dotenv>=1.1.0` - Environment variable management

## ⚡ Quick Start

### 1. Installation
```bash
# Clone repository
git clone https://github.com/yourusername/schwab-trading-automation.git
cd schwab-trading-automation

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the project root:

```bash
# Schwab API Configuration
SCHWAB_CLIENT_ID=your_client_id_here
SCHWAB_CLIENT_SECRET=your_client_secret_here
CALLBACK_URL=https://127.0.0.1:8182/callback

# Optional: Custom paths and settings
TOKEN_PATH=token.json
OUTPUT_FILE=filled_orders.csv
CUTOFF_DATE=2024-06-15T00:00:00+00:00

# Databricks Configuration (for data pipeline features)
DATABRICKS_PROFILE=mypharos
DATABRICKS_REMOTE_PATH=/Volumes/workspace/default/landing/filled_orders.csv
DATABRICKS_JOB_ID=939121727711316

# Optional: Logging configuration
LOG_LEVEL=INFO
```

### 3. Databricks Setup (Optional)
If using data pipeline features:

```bash
# Configure Databricks CLI
databricks auth login --host https://your-databricks-workspace.cloud.databricks.com

# Verify connection
databricks auth profiles
```

## 📖 Usage

### Order Export (Data Pipeline)
Export recent filled orders to CSV and upload to Databricks:

```bash
cd schwab-proj
python3 order_export.py
```

**Features:**
- ✅ Incremental extraction (only new orders since last run)
- ✅ Automatic Databricks upload when orders found
- ✅ Skip upload when no new orders
- ✅ Comprehensive logging

### Historical Data Processing
Transform historical trade data to match the export format:

```bash
cd schwab-proj
python3 transform_history.py
```

**Input:** `history.csv` (your historical trade data)  
**Output:** `historical_orders.csv` (Databricks-ready format)

### Trading Automation
Run automated stop-loss management:

```bash
cd schwab-proj
python3 order_manager.py
```

**Features:**
- Technical indicator calculations
- Automated order placement/replacement
- Risk management controls
- Dry-run mode for testing

## 📁 Project Structure

```
schwab-trading-automation/
├── requirements.txt          # Package dependencies
├── SETUP.md                 # Detailed setup guide  
├── readme.md               # This file
├── .env                    # Environment variables (create this)
├── schwab-proj/
│   ├── config.py           # Configuration management
│   ├── order_export.py     # Order export & Databricks pipeline
│   ├── order_manager.py    # Trading automation
│   ├── transform_history.py # Historical data processing
│   └── token.json          # Schwab API token (auto-generated)
├── last_execution.json     # Execution state tracking (auto-generated)
├── filled_orders.csv       # Export output (auto-generated)
└── historical_orders.csv   # Historical data output (auto-generated)
```

## 🔧 Configuration

### Schwab API Setup
1. Register for Schwab Developer API access
2. Create an application to get Client ID and Secret
3. Set callback URL to `https://127.0.0.1:8182/callback`
4. Add credentials to `.env` file

### Trading Configuration
Customize technical indicators and risk parameters in `config.py`:

```python
# Technical indicator parameters
sma_period: int = 20
ema_period: int = 10
atr_period: int = 14
chandelier_period: int = 22
chandelier_multiplier: float = 3.0

# Risk management
max_position_size: float = 10000.0
max_daily_trades: int = 10
min_price: float = 1.0
```

## 📊 Data Pipeline Features

### Incremental Execution
The order export maintains state in `last_execution.json`:

```json
{
  "last_execution_date": "2024-08-15T16:36:12.129000",
  "last_updated": "2024-08-15T16:36:15.312000"
}
```

Each run extracts only orders from the last execution date to current time, making it efficient for regular scheduled runs.

### Databricks Integration
Automatically:
1. Exports filled orders to CSV
2. Uploads to specified Databricks path
3. Triggers processing job
4. Skips upload if no new orders

Perfect for append-based data pipelines.

## 🚨 Important Notes

### API Limitations
- **Schwab API**: Only provides orders from last 60 days
- **Rate Limits**: Built-in retry logic respects API limits
- **Authentication**: Token auto-refresh handled automatically

### Data Pipeline Considerations
- First run extracts maximum available data (60 days)
- Subsequent runs extract incrementally
- Empty runs don't trigger Databricks operations
- Historical data processing handles data older than 60 days

## 🐛 Troubleshooting

### Common Issues

1. **"Module not found" errors**
   ```bash
   # Ensure virtual environment is activated
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Schwab authentication issues**
   - Verify Client ID and Secret in `.env`
   - Check callback URL matches registration
   - Delete `token.json` to force re-authentication

3. **Databricks connection issues**
   ```bash
   # Reconfigure Databricks CLI
   databricks auth login --host https://your-workspace.cloud.databricks.com
   ```

### Logs
Check these files for debugging:
- `order_export.log` - Export operations and API calls
- `trading.log` - Trading operations and technical analysis

## 📈 Performance

### Typical Performance Metrics
- **Order Export**: ~2-3 minutes for 60 days of data
- **Historical Processing**: ~1 second for 200 transactions
- **Databricks Upload**: ~10-15 seconds per file
- **API Calls**: Respects rate limits with exponential backoff

## 🛡️ Security

- **Token Storage**: Schwab tokens stored locally in `token.json`
- **Environment Variables**: Sensitive data in `.env` (never committed)
- **HTTPS**: All API communications use HTTPS
- **OAuth2**: Industry-standard authentication flow

## 📝 License

[Add your license information here]

## 🤝 Contributing

[Add contributing guidelines here]

## 📞 Support

For issues and questions:
- Check the troubleshooting section above
- Review logs for detailed error messages
- Ensure all environment variables are properly set