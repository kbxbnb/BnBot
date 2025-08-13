# db_bootstrap.py
import os, sqlite3

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/trades.db")
cur = conn.cursor()

# Logs
cur.execute("""
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT,
  level TEXT,
  component TEXT,
  event TEXT,
  message TEXT,
  ticker TEXT
)
""")

# News
cur.execute("""
CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT,
  headline TEXT,
  sentiment TEXT,
  sentiment_score REAL,
  sentiment_source TEXT,
  news_time TEXT
)
""")

# Trades
cur.execute("""
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  news_id INTEGER,
  ticker TEXT,
  headline TEXT,
  sentiment TEXT,
  sentiment_score REAL,
  sentiment_source TEXT,
  entry_price REAL,
  entry_amount REAL,
  entry_time TEXT,
  exit_price REAL,
  exit_time TEXT,
  exit_reason TEXT,
  skip_reason TEXT,
  trailing_stop_loss REAL DEFAULT 10.0,
  market_close_exit INTEGER DEFAULT 1,
  peak_price REAL
)
""")

# Settings
cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('capital_mode','percent')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('capital_value','10')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('account_size','100000')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('paper_trading','true')")

# Capital usage
cur.execute("""
CREATE TABLE IF NOT EXISTS capital_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT,
  ticker TEXT,
  amount REAL
)
""")

# Trade events (audit: TSL changes, manual exit, etc.)
cur.execute("""
CREATE TABLE IF NOT EXISTS trade_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_id INTEGER,
  event TEXT,
  old_value TEXT,
  new_value TEXT,
  ts TEXT
)
""")

conn.commit()
conn.close()

# Importing this module is enough to ensure the DB exists.
