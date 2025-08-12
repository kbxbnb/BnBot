import sqlite3, json, datetime

DB_PATH = "data/trades.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def get_setting(key: str, default: str | None = None) -> str | None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    conn.commit(); conn.close()

def record_capital_usage(ticker: str, amount: float):
    conn = get_conn(); cur = conn.cursor()
    date = datetime.date.today().isoformat()
    cur.execute("INSERT INTO capital_usage(date,ticker,amount) VALUES(?,?,?)", (date, ticker, amount))
    conn.commit(); conn.close()
