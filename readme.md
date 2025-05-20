# Schwab Trading Automation

Automate the management of stop-loss sell orders for a portfolio of stocks using the Schwab API. This project calculates dynamic stop prices based on technical indicators and manages open orders for a list of tickers.

## Features

- Connects to Schwab API using OAuth2 authentication
- Retrieves account positions and open orders
- Calculates technical indicators:
  - 20-day Simple Moving Average (SMA)
  - 10-day Exponential Moving Average (EMA)
  - 14-day Average True Range (ATR)
  - Chandelier Exit stop
- Automatically places or replaces stop-loss sell orders based on indicator logic
- Supports dry-run mode for testing

## Requirements

- Python 3.7+
- Schwab API credentials
- [schwab-py](https://github.com/areed1192/schwab-py) library
- [python-dotenv](https://pypi.org/project/python-dotenv/)
- [requests-oauthlib](https://pypi.org/project/requests-oauthlib/)

## Setup

1. Clone this repository.
2. Install dependencies:
   ```sh
   pip install schwab-py python-dotenv requests-oauthlib