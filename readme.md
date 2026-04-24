# Schwab Trading Automation

A comprehensive Python project for automating Schwab trading operations, including order management, data export, and Databricks integration. This project provides both automated trading capabilities and efficient data pipeline functionality.

## 🚀 Features

### Trading Automation (`order_manager.py`)
- **OAuth2** with Schwab API; reads positions and open orders
- **Indicators**: SMA, EMA, ATR (e.g. for Chandelier Exit), EMA of lows for breakeven-style stops
- **Adaptive stops**: Profit / loss / breakeven branches; winner trailing uses `min(EMA, Chandelier)`
- **Peak giveback floor**: After a configurable gain threshold, persists peak unrealized return and raises the stop to at least a fraction of that peak (JSON state file)
- **Dry-run** via `DRY_RUN=true`

### Order Export & Data Pipeline (`order_export.py`)
- **Incremental Data Export**: Tracks last execution date for efficient extraction
- **Schwab API Integration**: Export filled orders with proper date range handling
- **Databricks Integration**: Automatic file upload and job triggering
- **Smart Skipping**: Skip uploads when no new orders found
- **CSV Export**: Clean, structured data format
- **Logging**: Structured logs for export and API errors

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
git clone <your-repo-url>
cd schwab-trading-automation

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment configuration

Create **`schwab-proj/.env`** (see [SETUP.md](SETUP.md)). Scripts use `load_dotenv()` from the **current working directory**, so run `order_export.py` / `order_manager.py` from `schwab-proj` unless you manage `.env` elsewhere.

Minimal Schwab variables:

```bash
SCHWAB_CLIENT_ID=your_client_id_here
SCHWAB_CLIENT_SECRET=your_client_secret_here
CALLBACK_URL=https://127.0.0.1:8182/callback
```

**Trading** (`order_manager.py`) also requires **`TICKERS`** (comma-separated), e.g. `TICKERS=AAPL,MSFT`. Optional: `DRY_RUN=true`, `TOKEN_PATH`, indicator and giveback variables (see Configuration below and `config.py`).

**Export** optional keys: `OUTPUT_FILE`, `CUTOFF_DATE`, `DATABRICKS_*`, logging keys as in [SETUP.md](SETUP.md).

### 3. Databricks Setup (Optional)
If using data pipeline features:

```bash
# Configure Databricks CLI
databricks auth login --host https://your-databricks-workspace.cloud.databricks.com

# Verify connection
databricks auth profiles
```

## Usage

All Python entry points expect you to run from **`schwab-proj`** so `.env`, `token.json`, and generated files resolve consistently:

```bash
cd schwab-trading-automation/schwab-proj
source ../.venv/bin/activate   # if you created the venv at the repo root
python3 …
```

### `order_export.py`

Fetches **filled** equity orders from Schwab since the last successful run, appends to `OUTPUT_FILE` (default `filled_orders.csv`), then—if that file contains new rows—uploads it to Databricks and triggers `DATABRICKS_JOB_ID`. On full success it may remove the local CSV and updates **`last_execution.json`**; if upload or job fails, the checkpoint is **not** advanced so the next run retries the same window.

**Required in `.env`:** `SCHWAB_CLIENT_ID`, `SCHWAB_CLIENT_SECRET`, `CALLBACK_URL` (same as other scripts).

**For Databricks upload + job:** `DATABRICKS_PROFILE`, `DATABRICKS_REMOTE_PATH`, `DATABRICKS_JOB_ID` must match a working CLI profile and workspace. If there are no new orders, the script exits successfully and skips upload.

```bash
cd schwab-proj
python3 order_export.py
```

Exit code **0** on success, **1** on validation failure, export failure, or Databricks failure.

### `order_manager.py`

For each symbol in **`TICKERS`** (comma-separated, required), loads positions and daily price history, computes adaptive stop levels, then **places or replaces** a GTC stop-loss sell for the full long quantity. Uses **`token.json`** (OAuth with `interactive=False` in code—you need a valid token file; obtain one via **schwab-py** / Schwab’s flow if missing).

**Required in `.env`:** Schwab trio above plus **`TICKERS`** (e.g. `TICKERS=AAPL,MSFT`).

**Recommended for testing:** `DRY_RUN=true` (logs actions without placing orders).

```bash
cd schwab-proj
python3 order_manager.py
```

Writes **`peak_state.json`** (and logs) under the same cwd. Exit **0** only if every configured ticker was processed without error.

### `transform_history.py`

Does **not** call Schwab. Reads **`history.csv`** in the current directory (default), writes **`historical_orders.csv`** in the export schema for offline / bulk loads.

```bash
cd schwab-proj
# put your broker export as history.csv here (or adjust paths in code)
python3 transform_history.py
```

Exit **0** if at least one valid stock trade row was written; **1** if the run failed or no valid rows were found.

## Project structure

Typical layout when you work from **`schwab-proj/`** (recommended):

```
schwab-trading-automation/
├── requirements.txt
├── SETUP.md
├── readme.md
├── LICENSE
├── schwab-proj/
│   ├── .env                    # Create here (gitignored)
│   ├── config.py
│   ├── order_export.py
│   ├── order_manager.py
│   ├── transform_history.py
│   ├── token.json              # OAuth token (auto-generated)
│   ├── peak_state.json         # Peak P&L for giveback (auto-generated)
│   ├── last_execution.json     # Export incremental state (auto-generated)
│   ├── filled_orders.csv       # Export output
│   ├── order_export.log
│   └── trading.log
```

Paths for `token.json`, logs, CSVs, and state files follow the **process working directory** (defaults above assume `cd schwab-proj` before running Python).

## 🔧 Configuration

### Schwab API Setup
1. Register for Schwab Developer API access
2. Create an application to get Client ID and Secret
3. Set callback URL to `https://127.0.0.1:8182/callback`
4. Add credentials to `schwab-proj/.env` (or the cwd you run from)

### Trading configuration

Defaults and env overrides live in `schwab-proj/config.py` (`TradingConfig` / `load_trading_config`). Examples:

```python
sma_period: int = 20
ema_period: int = 10
breakeven_ema_period: int = 5
atr_period: int = 14
chandelier_period: int = 22
chandelier_multiplier: float = 3.0
profit_threshold: float = 0.05
loss_threshold: float = -0.03
max_loss_percent: float = 0.05
```

Peak profit giveback (optional env overrides; see `config.py` defaults):

| Variable | Default | Meaning |
|----------|---------|---------|
| `GIVEBACK_PCT` | `0.25` | Fraction of peak **gain** you may give back; stop floor uses `peak * (1 - GIVEBACK_PCT)` in return space. |
| `GIVEBACK_ACTIVATION_PCT` | `0.20` | Arm peak tracking once unrealized P&L reaches this return. |
| `PEAK_STATE_PATH` | `peak_state.json` | JSON file (created next to the process working directory) storing per-symbol `avg_cost` and `peak_pnl_pct` across runs. |

The order manager prunes this file when you no longer hold a symbol; average-cost drift beyond a small epsilon resets the peak for that lot.

## 📊 Data Pipeline Features

### Incremental execution

`order_export.py` stores the last successful export window in **`last_execution.json`** next to the script (same cwd rules as other generated files). Each run fetches orders after that timestamp through now.

### Databricks Integration
Automatically:
1. Exports filled orders to CSV
2. Uploads to specified Databricks path
3. Triggers processing job
4. Skips upload if no new orders

Perfect for append-based data pipelines.

## 🚨 Important Notes

### API limitations
- **Schwab**: Order history is limited to roughly the last **60 days** (Schwab API constraint).
- **Authentication**: Token refresh is handled by **schwab-py** once `token.json` exists; delete it to re-authenticate.

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
   - Confirm `.env` is in `schwab-proj` (or cwd) and contains Client ID, Secret, and callback URL
   - Callback URL must match your Schwab developer app
   - Delete `schwab-proj/token.json` (or your `TOKEN_PATH`) to force a new OAuth flow

3. **Databricks connection issues**
   ```bash
   # Reconfigure Databricks CLI
   databricks auth login --host https://your-workspace.cloud.databricks.com
   ```

### Logs

With default logging, files are created in the **current working directory** (e.g. `schwab-proj/order_export.log`, `schwab-proj/trading.log`).

## Security

- Store Schwab tokens in `token.json` (gitignored) and secrets only in `.env` (gitignored).
- API traffic uses HTTPS; OAuth2 is handled by **schwab-py**.

## License

This project is licensed under the MIT License; see [LICENSE](LICENSE).

## Issues

Use your repository’s issue tracker. For local failures, check the troubleshooting section and the log files named above.