import os, sqlite3, math
from datetime import datetime, timezone
from utils.sentiment import score_sentiment
from utils.price import fetch_intraday_bars, calc_vwap, calc_rvol, breaks_recent_resistance
from utils.db import get_setting, record_capital_usage
from utils.broker import get_account_balance_alpaca
from utils.alerts import send_email, send_telegram

DB_PATH = "data/trades.db"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_account_params():
    mode = get_setting("capital_mode","percent")  # 'percent' or 'dollar'
    value = float(get_setting("capital_value","10"))
    acct  = float(get_setting("account_size","100000"))
    if mode == "percent":
        per_trade = acct * (value/100.0)
    else:
        per_trade = value
    return acct, per_trade

def latest_price_from_df(df):
    return float(df["close"].iloc[-1])

def try_place_trade(cur, ticker, headline, sentiment, score, source, entry_price, per_trade_usd):
    # For simplicity: buy 'amount' dollars worth at entry_price
    shares = max(1, math.floor(per_trade_usd / max(entry_price, 0.01)))
    notional = shares * entry_price

    # Insert trade
    cur.execute("""
      INSERT INTO trades (ticker, headline, sentiment, sentiment_score, sentiment_source,
                          entry_price, entry_amount, entry_time, trailing_stop_loss, market_close_exit, peak_price)
      VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), 10.0, 1, ?)
    """, (ticker, headline, sentiment, score, source, entry_price, notional, entry_price))
    record_capital_usage(ticker, notional)

    # Alerts
    body = f"✅ ENTRY {ticker}\nPrice: {entry_price:.2f}\nNotional: ${notional:,.2f}\nSentiment: {sentiment} ({score}) via {source}\nHeadline: {headline}"
    send_email(f"BnBot Entry {ticker}", body)
    send_telegram(body)

def log_skip(cur, ticker, headline, reason, sentiment, score, source):
    cur.execute("""
      INSERT INTO trades (ticker, headline, sentiment, sentiment_score, sentiment_source, entry_time, skip_reason)
      VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
    """, (ticker, headline, sentiment, score, source, reason))
    body = f"⛔ SKIP {ticker}\nReason: {reason}\nSentiment: {sentiment} ({score}) via {source}\nHeadline: {headline}"
    send_email(f"BnBot Skip {ticker}", body)
    send_telegram(body)

def run_pipeline_once():
    acct, per_trade = get_account_params()
    bal = get_account_balance_alpaca() or {"buying_power": acct}
    available = float(bal.get("buying_power", acct))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Fetch latest unprocessed news (not used in trades table yet)
    cur.execute("""
      SELECT n.id, n.ticker, n.headline, n.sentiment, n.sentiment_score, n.sentiment_source, n.news_time
      FROM news n
      WHERE n.id NOT IN (SELECT COALESCE(news_id,0) FROM trades)
      ORDER BY n.news_time DESC
      LIMIT 50
    """)
    rows = cur.fetchall()

    for news_id, ticker, headline, bz_sent, bz_score, bz_source, news_time in rows:
        # sentiment (with benzinga prefer)
        sentiment, score, source = score_sentiment(headline, {"sentiment": bz_sent} if bz_sent else None)
        if sentiment not in ("bullish","very bullish"):
            log_skip(cur, ticker, headline, "Sentiment not bullish", sentiment, score, source)
            continue

        # fetch price data
        df = fetch_intraday_bars(ticker, timeframe="5Min", limit=120)
        if df is None:
            log_skip(cur, ticker, headline, "No price data", sentiment, score, source)
            continue

        # indicators
        vwap = calc_vwap(df).iloc[-1]
        rvol = calc_rvol(df, window=30)
        above_vwap = df["close"].iloc[-1] > vwap
        resistance_break = breaks_recent_resistance(df, lookback=20)
        if not (above_vwap and rvol > 1.5 and resistance_break):
            log_skip(cur, ticker, headline, "VWAP/RVOL/Resistance not met", sentiment, score, source)
            continue

        # place trade
        entry_price = df["close"].iloc[-1]
        # Check available capital
        if per_trade > available:
            log_skip(cur, ticker, headline, f"Insufficient capital: need ${per_trade:,.2f}, have ${available:,.2f}", sentiment, score, source)
            continue
        try_place_trade(cur, ticker, headline, sentiment, score, source, entry_price, per_trade_usd=per_trade)
        available -= per_trade

        # link news_id to trade
        cur.execute("UPDATE trades SET news_id=? WHERE rowid=last_insert_rowid()", (news_id,))

    conn.commit()
    conn.close()
