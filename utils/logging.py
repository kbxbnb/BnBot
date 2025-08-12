import sqlite3
from datetime import datetime, timezone

DB_PATH = "data/trades.db"

def log_db(level: str, component: str, event: str, message: str, ticker: str | None = None):
    """Write a single log line to the DB (UTC timestamp)."""
    ts = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (timestamp, level, component, event, message, ticker) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, level, component, event, message, ticker),
    )
    conn.commit()
    conn.close()
