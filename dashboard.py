import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import os, sqlite3
from datetime import datetime, timedelta
import pandas as pd
import pytz
import db_bootstrap  # executes and creates tables on import
import streamlit as st
from utils.price import fetch_intraday_bars

st.set_page_config(page_title="BnBot Dashboard", layout="wide")
os.makedirs("data", exist_ok=True)

PAC = pytz.timezone("US/Pacific")

def to_pt(ts):
    if ts is None or pd.isna(ts): return None
    return (pd.to_datetime(ts, utc=True).tz_convert(PAC).strftime("%Y-%m-%d %H:%M:%S"))

def roi(entry, exit_):
    if not entry or not exit_ or pd.isna(entry) or pd.isna(exit_) or entry == 0:
        return None
    return round((exit_ - entry) / entry * 100.0, 2)

def holding(entry_ts, exit_ts):
    if pd.isna(entry_ts) or pd.isna(exit_ts): return None
    d = pd.to_datetime(exit_ts) - pd.to_datetime(entry_ts)
    return str(d).split(".")[0]

# DB
try:
    conn = sqlite3.connect("data/trades.db", check_same_thread=False)
    cur = conn.cursor()
except Exception as e:
    st.error(f"Failed to connect to DB: {e}")
    st.stop()

tab_today, tab_prev, tab_bt, tab_logs, tab_heatmap, tab_settings = st.tabs([
    "🗓️ Today","📁 Skipped / Closed Trades","📉 Run Backtest","📜 Logs","🌡️ Heatmap","⚙️ Settings"
])

# --- SETTINGS TAB ---
with tab_settings:
    st.subheader("⚙️ Capital Settings")
    cur.execute("SELECT value FROM settings WHERE key='capital_mode'"); mode = (cur.fetchone() or ["percent"])[0]
    cur.execute("SELECT value FROM settings WHERE key='capital_value'"); value = float((cur.fetchone() or ["10"])[0])
    cur.execute("SELECT value FROM settings WHERE key='account_size'"); acct  = float((cur.fetchone() or ["100000"])[0])
    cur.execute("SELECT value FROM settings WHERE key='paper_trading'"); paper = (cur.fetchone() or ["true"])[0]

    c1,c2,c3,c4 = st.columns(4)
    mode_new = c1.selectbox("Capital mode", ["percent","dollar"], index=0 if mode=="percent" else 1)
    value_new = c2.number_input("Capital value (%, or $)", value=value, min_value=0.0)
    acct_new  = c3.number_input("Account size ($)", value=acct, min_value=0.0)
    paper_new = c4.selectbox("Trading mode", ["paper","live"], index=0 if paper.lower()=="true" else 1)

    if st.button("Save Settings"):
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('capital_mode',?)", (mode_new,))
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('capital_value',?)", (str(value_new),))
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('account_size',?)", (str(acct_new),))
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('paper_trading',?)", ("true" if paper_new=="paper" else "false",))
        conn.commit()
        st.success("Settings saved.")

# --- TODAY TAB ---
if hasattr(st, "autorefresh"): st.autorefresh(interval=30_000, key="today_refresh")
with tab_today:
    st.title("📈 BnBot Dashboard")

    # PnL summary (simple aggregation)
    st.markdown("#### PnL Summary")

# Daily Capital Usage (by ticker)
st.markdown("#### Capital Usage (Today)")
try:
    df_cap = pd.read_sql("""
        SELECT ticker, SUM(amount) as used
        FROM capital_usage
        WHERE date = DATE('now')
        GROUP BY ticker
        ORDER BY used DESC
    """, conn)
    if df_cap.empty:
        st.info("No capital usage recorded today.")
    else:
        st.dataframe(df_cap, use_container_width=True)
except Exception as e:
    st.info("Capital usage not available yet.")

    try:
        dft = pd.read_sql("SELECT entry_price, exit_price FROM trades WHERE exit_price IS NOT NULL", conn)
        total_pnl = 0.0
        if not dft.empty:
            dft["pnl"] = dft.apply(lambda r: (r["exit_price"]-r["entry_price"]) if pd.notna(r["exit_price"]) and pd.notna(r["entry_price"]) else 0.0, axis=1)
            total_pnl = round(dft["pnl"].sum(), 2)
        c1,c2 = st.columns(2)
        c1.metric("Total PnL (All time)", f"${total_pnl:,.2f}")
        # Daily PnL
        dfd = pd.read_sql("""
            SELECT entry_price, exit_price FROM trades
            WHERE DATE(COALESCE(exit_time, entry_time)) = DATE('now')
        """, conn)
        day_pnl = 0.0
        if not dfd.empty:
            dfd["pnl"] = dfd.apply(lambda r: (r["exit_price"]-r["entry_price"]) if pd.notna(r["exit_price"]) and pd.notna(r["entry_price"]) else 0.0, axis=1)
            day_pnl = round(dfd["pnl"].sum(), 2)
        c2.metric("PnL (Today)", f"${day_pnl:,.2f}")
    except Exception as e:
        st.info("PnL metrics unavailable yet.")

    st.subheader("📰 Live News (Today)")
    try:
        q = """
        SELECT ticker, headline AS news, sentiment, sentiment_score, sentiment_source, news_time
        FROM news
        WHERE DATE(news_time) = DATE('now')
        ORDER BY news_time DESC
        LIMIT 50
        """
        df_news = pd.read_sql(q, conn)
        if not df_news.empty:
            df_news = df_news.rename(columns={
                "news":"News Headline","sentiment":"Sentiment","sentiment_score":"Score","sentiment_source":"Sentiment Source"
            })
            st.dataframe(df_news.head(10), height=300, use_container_width=True)
        else:
            st.info("No news for today yet.")
    except Exception as e:
        st.warning(f"Could not load news: {e}")

    st.subheader("📊 Open Trades")
    fcol1, fcol2 = st.columns(2)
    ticker_filter = fcol1.text_input("Filter by Ticker (e.g., AAPL,TSLA)").upper().replace(' ','')
    sent_filter = fcol2.selectbox("Filter by Sentiment", ["All","bullish","bearish","neutral"])
    try:
        df_open = pd.read_sql("SELECT rowid as rid, * FROM trades WHERE exit_price IS NULL ORDER BY entry_time DESC", conn)
        if not df_open.empty:
            if ticker_filter:
                keep = [t.strip() for t in ticker_filter.split(',') if t.strip()]
                df_open = df_open[df_open['ticker'].isin(keep)] if keep else df_open
            if sent_filter != 'All':
                df_open = df_open[df_open['sentiment'] == sent_filter]
            df_open["Entry Time (PT)"] = df_open["entry_time"]
            show = ["ticker","headline","sentiment","sentiment_score","entry_amount","entry_price","Entry Time (PT)","trailing_stop_loss","market_close_exit"]
            # Compute Unrealized PnL (on-demand)
            if st.button('Refresh Unrealized PnL'):
                upnl = []
                for _, r in df_open.iterrows():
                    dfp = fetch_intraday_bars(r['ticker'], timeframe='5Min', limit=10)
                    if dfp is None or dfp.empty:
                        upnl.append(None)
                    else:
                        last = float(dfp['close'].iloc[-1])
                        qty = (r['entry_amount'] or 0.0) / max(r['entry_price'] or 1e-9, 1e-9)
                        upnl.append(round((last - (r['entry_price'] or 0.0)) * qty, 2))
                df_open['Unrealized PnL'] = upnl
            st.dataframe(df_open[show + (['Unrealized PnL'] if 'Unrealized PnL' in df_open.columns else [])], use_container_width=True)

            # TSL adjust & Market Close toggle by trade ID
            st.markdown("**Adjust Trailing Stop Loss (TSL) and Market Close Exit**")
            rid = st.selectbox("Select Trade ID", df_open["rid"].tolist())
            new_tsl = st.number_input("TSL %", min_value=1.0, max_value=50.0, value=float(df_open.loc[df_open["rid"]==rid,"trailing_stop_loss"].iloc[0]))
            mkt_toggle = st.selectbox("Market Close Exit", ["Enabled","Disabled"],
                                      index=0 if int(df_open.loc[df_open["rid"]==rid,"market_close_exit"].iloc[0])==1 else 1)
            if st.button("Apply"):
                # Fetch previous values for audit
                prev = pd.read_sql(f"SELECT trailing_stop_loss, market_close_exit FROM trades WHERE rowid={int(rid)}", conn)
                prev_tsl = float(prev['trailing_stop_loss'].iloc[0]) if not prev.empty else None
                prev_mkt = int(prev['market_close_exit'].iloc[0]) if not prev.empty else None
                cur.execute("UPDATE trades SET trailing_stop_loss=?, market_close_exit=? WHERE rowid=?",
                            (new_tsl, 1 if mkt_toggle=="Enabled" else 0, int(rid)))
                # Log event
                cur.execute("INSERT INTO trade_events(trade_id, event, old_value, new_value, ts) VALUES(?,?,?,?, datetime('now'))",
                            (int(rid), 'tsl_or_moc_change', str({'tsl': prev_tsl, 'moc': prev_mkt}), str({'tsl': new_tsl, 'moc': 1 if mkt_toggle=='Enabled' else 0})))
                conn.commit()
                st.success("Updated.")

            # Manual exit
            st.markdown("**Manual Exit**")
            rid2 = st.selectbox("Select Trade ID to Close", df_open["rid"].tolist(), key="manual_exit")
            if st.button("Confirm Manual Exit"):
                # For demo: set exit at same price
                ep = float(df_open.loc[df_open["rid"]==rid2,"entry_price"].iloc[0])
                cur.execute("UPDATE trades SET exit_price=?, exit_time=datetime('now'), exit_reason=? WHERE rowid=?",
                            (ep, "manual_exit", int(rid2)))
                conn.commit()
                st.success("Trade closed manually.")
        else:
            st.info("No open trades.")
    except Exception as e:
        st.warning(f"Error loading open trades: {e}")

    st.subheader("✅ Skipped / Closed Trades (Today)")
    f2c1, f2c2 = st.columns(2)
    t_filter2 = f2c1.text_input("Filter by Ticker (Today)", key='t2').upper().replace(' ','')
    s_filter2 = f2c2.selectbox("Filter by Sentiment (Today)", ["All","bullish","bearish","neutral"], key='s2')
    try:
        q = """
        SELECT * FROM trades
        WHERE (exit_price IS NOT NULL OR skip_reason IS NOT NULL)
          AND DATE(COALESCE(exit_time, entry_time)) = DATE('now')
        ORDER BY COALESCE(exit_time, entry_time) DESC
        """
        df_today = pd.read_sql(q, conn)
        if not df_today.empty:
            if t_filter2:
                keep = [t.strip() for t in t_filter2.split(',') if t.strip()]
                df_today = df_today[df_today['ticker'].isin(keep)] if keep else df_today
            if s_filter2 != 'All':
                df_today = df_today[df_today['sentiment'] == s_filter2]
            df_today["Entry Time (PT)"] = df_today["entry_time"]
            df_today["Exit Time (PT)"] = df_today["exit_time"]
            df_today["ROI (%)"] = df_today.apply(lambda r: roi(r.get("entry_price"), r.get("exit_price")), axis=1)
            df_today["Holding Time"] = df_today.apply(lambda r: None if pd.isna(r.get("exit_time")) else (pd.to_datetime(r.get("exit_time")) - pd.to_datetime(r.get("entry_time"))), axis=1)
            df_today["Holding Time"] = df_today["Holding Time"].astype(str).str.replace("NaT","")
            df_today["Exit/Skip Reason"] = df_today[["exit_reason","skip_reason"]].fillna("").agg(lambda x: x[0] or x[1], axis=1)
            show = ["ticker","headline","sentiment","sentiment_score","entry_amount","entry_price","Entry Time (PT)",
                    "exit_price","Exit Time (PT)","ROI (%)","Exit/Skip Reason","Holding Time"]
            st.dataframe(df_today[show], use_container_width=True)
        else:
            st.info("No skipped or closed trades today.")
    except Exception as e:
        st.warning(f"Error loading today's skipped/closed trades: {e}")

with tab_prev:
    st.subheader("📁 Skipped / Closed Trades (Previous)")
    try:
        q = """
        SELECT * FROM trades
        WHERE (exit_price IS NOT NULL OR skip_reason IS NOT NULL)
          AND DATE(COALESCE(exit_time, entry_time)) < DATE('now')
        ORDER BY COALESCE(exit_time, entry_time) DESC
        """
        df_prev = pd.read_sql(q, conn)
        if not df_prev.empty:
            df_prev["Entry Time (PT)"] = df_prev["entry_time"]
            df_prev["Exit Time (PT)"] = df_prev["exit_time"]
            df_prev["ROI (%)"] = df_prev.apply(lambda r: roi(r.get("entry_price"), r.get("exit_price")), axis=1)
            df_prev["Holding Time"] = df_prev.apply(lambda r: None if pd.isna(r.get("exit_time")) else (pd.to_datetime(r.get("exit_time")) - pd.to_datetime(r.get("entry_time"))), axis=1)
            df_prev["Holding Time"] = df_prev["Holding Time"].astype(str).str.replace("NaT","")
            df_prev["Exit/Skip Reason"] = df_prev[["exit_reason","skip_reason"]].fillna("").agg(lambda x: x[0] or x[1], axis=1)
            show = ["ticker","headline","sentiment","sentiment_score","entry_amount","entry_price","Entry Time (PT)",
                    "exit_price","Exit Time (PT)","ROI (%)","Exit/Skip Reason","Holding Time"]
            st.dataframe(df_prev[show], use_container_width=True)
        else:
            st.info("No older skipped/closed trades.")
    except Exception as e:
        st.warning(f"Error loading previous skipped/closed trades: {e}")

with tab_bt:
    st.subheader("📉 Run Backtest")
    from_dt = st.date_input("From Date", value=datetime.today() - timedelta(days=7))
    to_dt   = st.date_input("To Date",   value=datetime.today())
    tickers = st.text_input("Tickers (comma-separated, optional)")
    rvol_thr = st.number_input("RVOL Threshold", value=1.5, min_value=0.5, max_value=5.0, step=0.1)
    if st.button("Run Backtest"):
        cmd = f"python3 backtest_runner.py {from_dt} {to_dt} '{tickers}' {rvol_thr}"
        os.system(cmd)
        st.success("Backtest finished. Scroll down for results.")

    # Show latest backtest outputs if present
    import glob
    files = sorted(glob.glob('data/backtest_*_summary.json'))
    if files:
        latest = files[-1]
        import json
        with open(latest, 'r') as f:
            summary = json.load(f)
        st.markdown("### Summary")
        st.json(summary)
        csv = latest.replace('_summary.json', '.csv')
        if os.path.exists(csv):
            st.markdown("### Results")
            df_bt = pd.read_csv(csv)
            st.dataframe(df_bt.head(1000), use_container_width=True)
            with open(csv, 'rb') as f:
                st.download_button("Download CSV", f, file_name=csv.split('/')[-1])
    else:
        st.info("Run a backtest to see results here.")

import logs_tab
with tab_logs:
    logs_tab.render(conn)

with tab_heatmap:
    st.subheader("🌡️ News Sentiment Heatmap (7 days)")
    try:
        df_h = pd.read_sql("""
            SELECT ticker, DATE(news_time) as day, AVG(COALESCE(sentiment_score,0)) as avg_score
            FROM news
            WHERE DATE(news_time) >= DATE('now','-6 days')
            GROUP BY ticker, day
            ORDER BY day DESC
        """, conn)
        if df_h.empty:
            st.info("No data for heatmap yet.")
        else:
            # simple pivot view
            pv = df_h.pivot(index="ticker", columns="day", values="avg_score").fillna(0.0)
            st.dataframe(pv, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render heatmap: {e}")

conn.close()
