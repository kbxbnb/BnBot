# BnBot v6 Full Release

Features:
- Polls Benzinga every 10s and stores news (PT timestamps)
- Sentiment source tracking (Benzinga / FinBERT / VADER) [pipeline hooks ready]
- Entry filters: VWAP, RVOL, Resistance [pipeline hooks ready]
- TSL & Market close exit [pipeline hooks ready]
- Streamlit Dashboard:
  - 🗓️ Today tab: Live News → Open Trades → Skipped/Closed (Today)
  - 📁 Skipped/Closed Trades (Previous)
  - 📉 Run Backtest
  - 📜 Logs (top shows latest Benzinga REQUEST/RESPONSE)
- SQLite DB with `news`, `trades`, `logs`

## Setup

1) Fill `.streamlit/secrets.toml` with keys:
   ```toml
   BENZINGA_API_KEY = "..."
   ALPACA_API_KEY = "..."
   ALPACA_SECRET_KEY = "..."
   EMAIL_HOST = "smtp.example.com"
   EMAIL_PORT = 587
   EMAIL_USERNAME = "you@example.com"
   EMAIL_PASSWORD = "app_password"
   TELEGRAM_BOT_TOKEN = "..."
   TELEGRAM_CHAT_ID = "..."
   ```

2) (Optional) Initialize DB tables:
   ```bash
   python db_bootstrap.py
   ```

3) Run news poller locally:
   ```bash
   python news_fetcher.py
   ```

4) Launch dashboard:
   ```bash
   streamlit run dashboard.py
   ```

Deploy on Streamlit Cloud:
- Main file: `dashboard.py`
- Add secrets via Settings → Secrets


## Backtester

Run from CLI:
```bash
python backtest_runner.py 2025-08-01 2025-08-08
# optional: specify tickers and RVOL threshold
python backtest_runner.py 2025-08-01 2025-08-08 AAPL,TSLA 1.8
```

What it does:
- Fetches Benzinga news in date range (optionally filtered by tickers)
- Scores sentiment (Benzinga tag → FinBERT → VADER)
- Pulls Alpaca OHLCV intraday bars
- Applies entry rules (VWAP > price, RVOL > threshold, resistance break)
- Simulates TSL exit or timed exit
- Saves `data/backtest_YYYY-MM-DD_YYYY-MM-DD.csv` + `_summary.json`

Use the **Run Backtest** tab in the dashboard to configure and view results, and download the CSV.
