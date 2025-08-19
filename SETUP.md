# Schwab Trading Automation Setup Guide

## Required Packages

### Core Dependencies

The project requires the following Python packages:

- **schwab-py** (>=1.5.0) - Schwab API client
- **databricks-sdk** (>=0.43.0) - Databricks integration
- **python-dotenv** (>=1.1.0) - Environment variable management

### Installation

1. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Alternative - Install individually**:
   ```bash
   pip install schwab-py>=1.5.0
   pip install databricks-sdk>=0.43.0
   pip install python-dotenv>=1.1.0
   ```

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the project root with:

```bash
# Schwab API Configuration
SCHWAB_CLIENT_ID=your_client_id_here
SCHWAB_CLIENT_SECRET=your_client_secret_here
CALLBACK_URL=https://127.0.0.1:8182/callback

# Optional: Custom paths and settings
TOKEN_PATH=token.json
OUTPUT_FILE=filled_orders.csv
CUTOFF_DATE=2024-06-15T00:00:00+00:00

# Databricks Configuration
DATABRICKS_PROFILE=mypharos
DATABRICKS_REMOTE_PATH=/Volumes/workspace/default/landing/filled_orders.csv
DATABRICKS_JOB_ID=939121727711316

# Optional: Logging configuration
LOG_LEVEL=INFO
```

### Databricks Setup

1. **Configure Databricks CLI**:
   ```bash
   databricks auth login --host https://your-databricks-workspace.cloud.databricks.com
   ```

2. **Verify connection**:
   ```bash
   databricks auth profiles
   ```

## Python Version Requirements

- **Minimum**: Python 3.9
- **Recommended**: Python 3.11 or later
- **Tested on**: Python 3.12

## File Structure

```
schwab-trading-automation/
├── requirements.txt          # Package dependencies
├── SETUP.md                 # This setup guide
├── .env                     # Environment variables (create this)
├── schwab-proj/
│   ├── config.py           # Configuration management
│   ├── order_export.py     # Main export script
│   ├── order_manager.py    # Trading operations
│   ├── transform_history.py # Historical data processing
│   └── token.json          # Schwab API token (auto-generated)
└── last_execution.json      # Execution state (auto-generated)
```

## Verification

Run the following to verify your setup:

```bash
cd schwab-proj
python3 -c "from config import validate_environment; print('✅ Environment OK' if validate_environment() else '❌ Environment issues')"
```

## Usage

### Order Export
```bash
cd schwab-proj
python3 order_export.py
```

### Historical Data Processing
```bash
cd schwab-proj
python3 transform_history.py
```

## Troubleshooting

### Common Issues

1. **"Module not found" errors**: Ensure virtual environment is activated and packages are installed
2. **Schwab authentication issues**: Check your client ID and secret in `.env`
3. **Databricks connection issues**: Verify your Databricks CLI configuration
4. **API rate limits**: The script includes built-in retry logic and respects API limits

### Logs

Check these log files for debugging:
- `order_export.log` - Export operations
- `trading.log` - Trading operations (if using order_manager.py)
