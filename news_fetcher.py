import os
import time
import json
import sqlite3
import requests
import pytz
import xmltodict

from datetime import timezone
from dateutil import parser

# If your project already has this helper, keep it:
from utils.logging import log_db  # writes to logs table (timestamp, level, component, event, message, ticker)

DB_PATH = "data/trades.db"

# Read Benzinga key from Streamlit secrets/env; fallback string is harmless for local dev
BENZINGA_API_KEY = (
    os.getenv("BENZINGA_API_KEY")
    or os.getenv("BENZINGA__API_KEY")
    or "YOUR_BENZINGA_API_KEY"
)

# Optional: limit to a watchlist (great for debugging)
# e.g., export BENZINGA_TICKERS="AAPL,TSLA,NVDA,MSFT"
TICKER_FILTER = os.getenv("BENZINGA_TICKERS", "").strip()

PT = pytz.timezone("US/Pacific")


# -----------------------
# DB bootstrap (idempotent)
# -----------------------
def ensure_tables():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
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
    conn.commit()
    conn.close()


# -----------------------
# Time + Ticker utilities
# -----------------------
def to_pt_str(ts_iso: str) -> str:
    """Convert any incoming timestamp string to 'YYYY-mm-dd HH:MM:SS' in Pacific Time."""
    dt = parser.parse(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PT).strftime("%Y-%m-%d %H:%M:%S")


def extract_tickers(article: dict) -> list[str]:
    """
    Return a list of uppercased tickers robust to JSON/XML variations.
    Handles:
      - JSON: article['stocks'] / ['tickers'] as list[str] or list[dict]
      - XML:  article['stocks']={'item': [...]} with str/dict items
    """
    tickers: list[str] = []

    # JSON-style keys first
    for key in ("stocks", "tickers"):
        val = article.get(key)
        if not val:
            continue
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    tickers.append(item.upper().strip())
                elif isinstance(item, dict):
                    cand = (
                        item.get("symbol")
                        or item.get("name")
                        or item.get("#text")
                        or item.get("value")
                    )
                    if isinstance(cand, str):
                        tickers.append(cand.upper().strip())
        elif isinstance(val, str):
            tickers += [x.strip().upper() for x in val.split(",") if x.strip()]

    # XML-style: {"stocks": {"item": ...}}
    sdict = article.get("stocks")
    if isinstance(sdict, dict) and not tickers:
        items = sdict.get("item")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    tickers.append(it.upper().strip())
                elif isinstance(it, dict):
                    cand = it.get("#text") or it.get("value")
                    if isinstance(cand, str):
                        tickers.append(cand.upper().strip())
        elif isinstance(items, str):
            tickers.append(items.upper().strip())

    # Clean + uniq
    clean = []
    for t in tickers:
        t = t.replace("$", "")
        if 1 <= len(t) <= 6 and t.isalnum():
            clean.append(t)
    return sorted(set(clean))


def normalize_article_for_log(a: dict) -> dict:
    """Minimal normalized record used for the Logs tab debug view."""
    headline = a.get("title") or a.get("headline") or ""
    created = a.get("created") or a.get("published") or a.get("time") or ""
    return {"headline": headline, "created": created, "tickers": extract_tickers(a)}


# -----------------------
# Response parsing
# -----------------------
def _parse_json_or_xml(resp) -> list[dict]:
    """Return a list of article dicts. Try JSON first, then XML."""
    # 1) Try JSON
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

    # 2) Fallback: XML
    try:
        parsed = xmltodict.parse(resp.text)
        items = parsed.get("result", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        articles = []
        for it in items:
            title = it.get("title") or ""
            created = it.get("created") or it.get("updated") or ""
            # Might contain <stocks><item>...</item></stocks>
            stocks = it.get("stocks")
            articles.append(
                {
                    "title": title,
                    "headline": title,
                    "created": created,
                    "stocks": stocks,  # keep raw; extract_tickers() can handle dict/list/str
                }
            )
        return articles
    except Exception:
        return []


# -----------------------
# DB insert
# -----------------------
def save_news_rows(articles: list[dict]) -> int:
    """
    Insert rows into news table.
    Skips:
      - missing headline/time
      - missing/unknown tickers
      - duplicate (ticker, headline)
    Emits an INGEST_SUMMARY_DETAILED log with counters.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inserted = 0
    seen = 0
    no_ticker = 0
    duplicates = 0
    time_parse_err = 0

    for a in articles:
        seen += 1

        headline = a.get("title") or a.get("headline") or ""
        news_time_iso = a.get("created") or a.get("published") or a.get("time") or ""
        if not headline or not news_time_iso:
            continue

        # time to PT
        try:
            news_time_pt = to_pt_str(news_time_iso)
        except Exception:
            time_parse_err += 1
            continue

        tickers = extract_tickers(a)
        if not tickers:
            no_ticker += 1
            continue

        for ticker in tickers:
            cur.execute("SELECT 1 FROM news WHERE ticker=? AND headline=?", (ticker, headline))
            if cur.fetchone():
                duplicates += 1
                continue

            cur.execute(
                """
                INSERT INTO news (ticker, headline, sentiment, sentiment_score, sentiment_source, news_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticker, headline, None, None, "benzinga", news_time_pt),
            )
            inserted += 1

    conn.commit()
    conn.close()

    # Detailed ingest log for the Logs tab
    log_db(
        "INFO",
        "benzinga",
        "INGEST_SUMMARY_DETAILED",
        json.dumps(
            {
                "seen": seen,
                "inserted": inserted,
                "no_ticker": no_ticker,
                "duplicates": duplicates,
                "time_parse_errors": time_parse_err,
            }
        ),
    )
    return inserted


# -----------------------
# One-shot fetch
# -----------------------
def fetch_and_log_once():
    ensure_tables()

    url = "https://api.benzinga.com/api/v2/news"
    params = {
        "token": BENZINGA_API_KEY,
        "pagesize": 50,
        "display_tickers": "true",
        "format": "json",  # prefer JSON
    }
    if TICKER_FILTER:
        params["tickers"] = TICKER_FILTER

    headers = {"Accept": "application/json"}

    # Log REQUEST
    try:
        log_db("API", "benzinga", "REQUEST", json.dumps({"url": url, "params": params}))
        start = time.time()
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        elapsed_ms = int((time.time() - start) * 1000)
    except Exception as e:
        log_db("ERROR", "benzinga", "REQUEST_ERROR", f"{type(e).__name__}: {e}")
        return

    # Parse
    articles = _parse_json_or_xml(resp)
    titles_sample = [(a.get("title") or a.get("headline") or "") for a in (articles or [])[:5]]

    # Log RESPONSE summary (even when status != 200)
    log_db(
        "API",
        "benzinga",
        "RESPONSE",
        json.dumps(
            {
                "request_url": resp.request.url if hasattr(resp, "request") else url,
                "status": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "items": len(articles or []),
                "titles_sample": titles_sample,
            }
        ),
    )

    if resp.status_code != 200:
        log_db(
            "ERROR",
            "benzinga",
            "RESPONSE_ERROR",
            json.dumps({"status": resp.status_code, "body": resp.text[:800]}),
        )
        return

    if articles:
        try:
            sample = normalize_article_for_log(articles[0])
            log_db("DEBUG", "benzinga", "PARSED_SAMPLE", json.dumps(sample))
        except Exception:
            pass
    else:
        log_db(
            "ERROR",
            "benzinga",
            "PARSE_ERROR",
            json.dumps({"error": "No articles parsed", "body_snip": resp.text[:800]}),
        )
        return

    try:
        inserted = save_news_rows(articles)
        log_db("INFO", "benzinga", "INGEST_SUMMARY", f"Inserted {inserted} news rows.")
    except Exception as e:
        log_db(
            "ERROR",
            "benzinga",
            "PARSE_ERROR",
            json.dumps({"error": f"{type(e).__name__}: {e}", "body_snip": resp.text[:800]}),
        )
        return


if __name__ == "__main__":
    ensure_tables()
    print("🚀 Polling Benzinga every 10s")
    while True:
        try:
            fetch_and_log_once()
        except Exception as e:
            # Final guard: never crash the loop
            log_db("ERROR", "benzinga", "UNHANDLED", f"{type(e).__name__}: {e}")
        time.sleep(10)