import os, sqlite3

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/trades.db")
cur = conn.cursor()

# Core tables
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

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS capital_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT,
  ticker TEXT,
  amount REAL
)
""")

# Ensure new columns exist on old DBs
def ensure_column(table, column, coltype):
    cur.execute("PRAGMA table_info(%s)" % table)
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

ensure_column("trades", "peak_price", "REAL")
ensure_column("trades", "trailing_stop_loss", "REAL")
ensure_column("trades", "market_close_exit", "INTEGER")

# Defaults
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('capital_mode','percent')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('capital_value','10')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('account_size','100000')")
cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('paper_trading','true')")

conn.commit()
conn.close()
print("✅ DB tables/columns ensured.")


# Trade events audit table (e.g., TSL changes, manual exits)
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
