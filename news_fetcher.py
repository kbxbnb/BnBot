import os, time, json, sqlite3, pytz, requests, xmltodict
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, level TEXT, component TEXT, event TEXT, message TEXT, ticker TEXT
        )
    """)
    conn.commit(); conn.close()

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
                """,
                (ticker, headline, None, None, "benzinga", news_time_pt)
            )
            inserted += 1
    conn.commit(); conn.close()
    return inserted

def _parse_json_or_xml(resp):
    """Return a list[dict] articles, normalizing XML shape when needed."""
    # Try JSON
    try:
        data = resp.json()
        if isinstance(data, dict) and "articles" in data:
            arts = data.get("articles") or []
            if isinstance(arts, list):
                return arts
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Fallback to XML
    try:
        parsed = xmltodict.parse(resp.text)
        items = parsed.get("result", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        articles = []
        for it in items:
            title = it.get("title") or ""
            # tickers might be under <stocks><item>...</item></stocks>
            stocks = []
            stocks_xml = (it.get("stocks") or {}).get("item")
            if isinstance(stocks_xml, list):
                stocks = [s for s in stocks_xml if s]
            elif isinstance(stocks_xml, str):
                stocks = [stocks_xml]
            created = it.get("created") or it.get("updated") or ""
            articles.append({
                "title": title,
                "headline": title,
                "stocks": stocks,
                "created": created
            })
        return articles
    except Exception:
        # give back empty to let caller handle logging
        return []

def fetch_and_log_once():
    ensure_tables()

    url = "https://api.benzinga.com/api/v2/news"
    params = {
        "token": BENZINGA_API_KEY,
        "pagesize": 50,
        "display_tickers": "true",
        "format": "json",                 # prefer JSON
    }
    headers = {"Accept": "application/json"}

    # Log REQUEST
    try:
        log_db("API", "benzinga", "REQUEST", json.dumps({"url": url, "params": params}))
        start = time.time()
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        elapsed_ms = int((time.time() - start) * 1000)
    except Exception as e:
        log_db("ERROR", "benzinga", "REQUEST_ERROR", f"{type(e).__name__}: {e}")
        return  # <-- inside function, OK

    # Parse RESP
    articles = _parse_json_or_xml(resp)
    titles_sample = [(a.get("title") or a.get("headline") or "") for a in (articles or [])[:5]]

    # Log RESPONSE summary (even if not 200 to see body)
    log_db("API", "benzinga", "RESPONSE", json.dumps({
        "request_url": resp.request.url if hasattr(resp, "request") else url,
        "status": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "items": len(articles or []),
        "titles_sample": titles_sample
    }))

    # On HTTP error, log detail and stop
    if resp.status_code != 200:
        log_db("ERROR", "benzinga", "RESPONSE_ERROR",
               json.dumps({"status": resp.status_code, "body": resp.text[:800]}))
        return  # <-- inside function, OK

    # If parsing failed/empty, log and stop
    if not articles:
        log_db("ERROR", "benzinga", "PARSE_ERROR",
               json.dumps({"error": "No articles parsed", "body_snip": resp.text[:800]}))
        return  # <-- inside function, OK

    # Save rows
    try:
        inserted = save_news_rows(articles)
        log_db("INFO", "benzinga", "INGEST_SUMMARY", f"Inserted {inserted} news rows.")
    except Exception as e:
        log_db("ERROR", "benzinga", "PARSE_ERROR",
               json.dumps({"error": f"{type(e).__name__}: {e}", "body_snip": resp.text[:800]}))
        # don't re-raise, just return
        return  # <-- inside function, OK

if __name__ == "__main__":
    ensure_tables()
    print("🚀 Polling Benzinga every 10s")
    while True:
        try:
            fetch_and_log_once()
        except Exception as e:
            # final guard so one bad loop doesn't kill the poller
            log_db("ERROR", "benzinga", "UNHANDLED", f"{type(e).__name__}: {e}")
        time.sleep(10)

