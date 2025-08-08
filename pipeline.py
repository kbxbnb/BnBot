
import sqlite3
from utils.sentiment import score_sentiment
from utils.trade_logic import confirm_trade_entry, execute_trade, log_skipped_trade

DB_PATH = "data/trades.db"

def run_pipeline():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get unprocessed news
    cur.execute("SELECT id, ticker, headline FROM news WHERE id NOT IN (SELECT news_id FROM trades WHERE news_id IS NOT NULL)")
    news_items = cur.fetchall()

    for news_id, ticker, headline in news_items:
        sentiment, score, source = score_sentiment(headline)
        passed_entry = confirm_trade_entry(ticker)

        if passed_entry:
            entry_price, entry_amount = execute_trade(ticker)
            cur.execute("""
                INSERT INTO trades (ticker, headline, sentiment, sentiment_score, sentiment_source, entry_price, entry_amount, entry_time, passed_resistance, exit_price, exit_time, exit_reason, roi, holding_time, news_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, NULL, NULL, NULL, NULL, NULL, ?)
            """, (ticker, headline, sentiment, score, source, entry_price, entry_amount, 1, news_id))
        else:
            log_skipped_trade(cur, ticker, headline, sentiment, score, source, reason="VWAP/RVOL/Resistance not met", news_id=news_id)

    conn.commit()
    conn.close()
