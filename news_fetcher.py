
import requests
import sqlite3
import time
import pytz
from datetime import datetime
from dateutil import parser
import os

BENZINGA_API_KEY = os.getenv("BENZINGA_API_KEY", "YOUR_BENZINGA_API_KEY")
DB_PATH = "data/trades.db"

def fetch_news():
    url = f"https://api.benzinga.com/api/v2/news"
    params = {
        "token": BENZINGA_API_KEY,
        "pagesize": 50,
        "categories": "stock",
        "display_tickers": "true"
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()
        return data.get("articles", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch news: {e}")
        return []

def convert_to_pacific(timestamp_str):
    utc = pytz.timezone("UTC")
    pacific = pytz.timezone("America/Los_Angeles")
    dt_utc = parser.parse(timestamp_str).astimezone(utc)
    return dt_utc.astimezone(pacific).strftime("%Y-%m-%d %H:%M:%S")

def save_news(articles):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for article in articles:
        headline = article.get("title", "")
        tickers = article.get("stocks", [])
        sentiment = article.get("sentiment", "")
        source = "benzinga"
        published_utc = article.get("created", "")
        try:
            news_time = convert_to_pacific(published_utc)
        except:
            continue

        for ticker in tickers:
            ticker = ticker.upper()
            # Check if already exists
            cur.execute("SELECT 1 FROM news WHERE ticker = ? AND headline = ?", (ticker, headline))
            if cur.fetchone():
                continue

            cur.execute("""
                INSERT INTO news (ticker, headline, sentiment, sentiment_score, sentiment_source, news_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ticker, headline, sentiment, None, source, news_time))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    while True:
        articles = fetch_news()
        if articles:
            save_news(articles)
        time.sleep(10)
