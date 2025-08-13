import db_bootstrap  # executes and creates tables on import
import os, time, json, sqlite3, pytz, requests
from datetime import timezone
from dateutil import parser
from utils.logging import log_db

DB_PATH = "data/trades.db"
BENZINGA_API_KEY = (
    os.getenv("BENZINGA_API_KEY")
    or os.getenv("BENZINGA__API_KEY")
    or "YOUR_BENZINGA_API_KEY"
)

PAC = pytz.timezone("US/Pacific")

def to_pt_str(ts_iso: str) -> str:
    dt = parser.parse(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PAC).strftime("%Y-%m-%d %H:%M:%S")

def ensure_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
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
    conn.commit()
    conn.close()

def save_news_rows(articles):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inserted = 0
    for a in articles:
        headline = a.get("title") or a.get("headline") or ""
        stocks = a.get("stocks") or a.get("tickers") or []
        news_time_iso = a.get("created") or a.get("published") or a.get("time") or ""
        if not headline or not stocks or not news_time_iso:
            continue
        try:
            news_time_pt = to_pt_str(news_time_iso)
        except Exception:
            continue
        for t in stocks:
            ticker = (t or "").upper().strip()
            if not ticker:
                continue
            # de-dupe by (ticker, headline)
            cur.execute("SELECT 1 FROM news WHERE ticker=? AND headline=?", (ticker, headline))
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO news (ticker, headline, sentiment, sentiment_score, sentiment_source, news_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (ticker, headline, None, None, "benzinga", news_time_pt)
            )
            inserted += 1
    conn.commit()
    conn.close()
    return inserted

def fetch_and_log_once():
    ensure_tables()
    url = "https://api.benzinga.com/api/v2/news"
    params = {
        "token": BENZINGA_API_KEY,
        "pagesize": 50,
        "display_tickers": "true",
    }
    # Log outgoing request
    try:
        log_db("API", "benzinga", "REQUEST", json.dumps({"url": url, "params": params}))
        start = time.time()
        resp = requests.get(url, params=params, timeout=15)
        elapsed_ms = int((time.time() - start) * 1000)
    except Exception as e:
        log_db("ERROR", "benzinga", "REQUEST_ERROR", f"{type(e).__name__}: {e}")
        return

    # Parse & log response
    try:
        data = resp.json()
        if isinstance(data, dict) and "articles" in data:
            articles = data.get("articles", [])
        else:
            articles = data if isinstance(data, list) else []

        titles_sample = [(a.get("title") or a.get("headline") or "") for a in articles[:5]]
        log_db("API", "benzinga", "RESPONSE", json.dumps({
            "request_url": resp.request.url,
            "status": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "items": len(articles),
            "titles_sample": titles_sample
        }))

        if resp.status_code != 200:
            log_db("ERROR", "benzinga", "RESPONSE_ERROR",
                   json.dumps({"status": resp.status_code, "body": resp.text[:800]}))
            return

        inserted = save_news_rows(articles)
        log_db("INFO", "benzinga", "INGEST_SUMMARY", f"Inserted {inserted} news rows.")
    except Exception as e:
        body_snip = None
        try:
            body_snip = resp.text[:800]
        except Exception:
            pass
        log_db("ERROR", "benzinga", "PARSE_ERROR",
               json.dumps({"error": f"{type(e).__name__}: {e}", "body_snip": body_snip}))

if __name__ == "__main__":
    print("🚀 Polling Benzinga every 10s")
    while True:
        fetch_and_log_once()
        time.sleep(10)
