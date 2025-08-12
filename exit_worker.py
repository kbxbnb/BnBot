import time, os, sqlite3
from datetime import datetime
import pytz
from utils.price import fetch_intraday_bars
from utils.alerts import send_email, send_telegram

DB_PATH = "data/trades.db"
PAC = pytz.timezone("US/Pacific")

def now_pt():
    return datetime.now(PAC)

def process_open_trades():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT rowid, ticker, entry_price, trailing_stop_loss, market_close_exit, peak_price FROM trades WHERE exit_price IS NULL")
    rows = cur.fetchall()
    for rid, ticker, entry_price, tsl, mkt_flag, peak in rows:
        # Fetch last price
        df = fetch_intraday_bars(ticker, timeframe="5Min", limit=10)
        if df is None or df.empty:
            continue
        last_price = float(df["close"].iloc[-1])

        # Update peak price
        peak_price = max(peak or entry_price or last_price, last_price)
        cur.execute("UPDATE trades SET peak_price=? WHERE rowid=?", (peak_price, rid))

        # Trailing stop logic
        if tsl is None:
            tsl = 10.0
        drop_pct = (peak_price - last_price) / peak_price * 100.0 if peak_price else 0.0
        if drop_pct >= float(tsl):
            # Exit at last price
            cur.execute("UPDATE trades SET exit_price=?, exit_time=datetime('now'), exit_reason=? WHERE rowid=?",
                        (last_price, f"tsl_{tsl}%", rid))
            conn.commit()
            body = f"🔻 EXIT (TSL) {ticker}\nExit Price: {last_price:.2f}\nTSL: {tsl}%"
            send_email(f"BnBot Exit (TSL) {ticker}", body)
            send_telegram(body)
            continue

        # Market close exit
        now = now_pt()
        if int(mkt_flag or 1) == 1:
            # 12:59:30 PT (close ~1pm PT for regular session)
            if now.hour > 12 or (now.hour == 12 and now.minute >= 59):
                cur.execute("UPDATE trades SET exit_price=?, exit_time=datetime('now'), exit_reason=? WHERE rowid=?",
                            (last_price, "market_close", rid))
                conn.commit()
                body = f"🔔 EXIT (Market Close) {ticker}\nExit Price: {last_price:.2f}"
                send_email(f"BnBot Exit (MOC) {ticker}", body)
                send_telegram(body)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    print("🧮 Exit worker running every 10s (TSL + Market Close)")
    while True:
        try:
            process_open_trades()
        except Exception as e:
            print("Exit worker error:", e)
        time.sleep(10)
