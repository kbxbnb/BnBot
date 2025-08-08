
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import pytz
import os

st.set_page_config(layout="wide", page_title="BnBot Dashboard")
st.title("📈 BnBot Dashboard")

# Ensure data folder exists
os.makedirs("data", exist_ok=True)

# Connect to DB
try:
    conn = sqlite3.connect("data/trades.db", check_same_thread=False)
except Exception as e:
    st.error(f"Failed to connect to DB: {e}")
    st.stop()

# Pacific time zone
pacific = pytz.timezone("US/Pacific")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📰 Live News", "📊 Trades", "📁 Skipped / Closed Trades", "📉 Run Backtest"
])

def format_time(t):
    return pd.to_datetime(t).tz_localize("UTC").tz_convert(pacific).strftime("%Y-%m-%d %H:%M:%S")

def calculate_roi(entry, exit):
    return round(((exit - entry) / entry) * 100, 2) if entry and exit else None

def calculate_holding(entry_time, exit_time):
    if pd.notnull(entry_time) and pd.notnull(exit_time):
        delta = pd.to_datetime(exit_time) - pd.to_datetime(entry_time)
        return str(delta)
    return None

with tab1:
    st.subheader("📰 Live News (Today)")
    try:
        df_news = pd.read_sql_query("""
            SELECT ticker, headline AS news, sentiment, sentiment_score, sentiment_source, news_time
            FROM news
            WHERE DATE(news_time) = DATE('now')
            ORDER BY news_time DESC
        """, conn)
        df_news["news_time"] = pd.to_datetime(df_news["news_time"]).dt.tz_localize("UTC").dt.tz_convert(pacific).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_news.head(10), height=300, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load news: {e}")

with tab2:
    st.subheader("📊 Still Open Trades")
    try:
        df_open = pd.read_sql_query("SELECT * FROM trades WHERE exit_price IS NULL", conn)
        if not df_open.empty:
            df_open["entry_time"] = df_open["entry_time"].apply(format_time)
            df_open = df_open[["ticker", "headline", "sentiment", "sentiment_score", "entry_amount", "entry_price", "entry_time"]]
            st.dataframe(df_open, use_container_width=True)
        else:
            st.info("No open trades.")
    except Exception as e:
        st.warning(f"Error loading open trades: {e}")

    st.subheader("✅ Skipped / Closed Trades (Today)")
    try:
        df_today = pd.read_sql_query("""
            SELECT * FROM trades
            WHERE (exit_price IS NOT NULL OR skip_reason IS NOT NULL)
              AND DATE(COALESCE(exit_time, entry_time)) = DATE('now')
            ORDER BY COALESCE(exit_time, entry_time) DESC
        """, conn)
        if not df_today.empty:
            df_today["entry_time"] = df_today["entry_time"].apply(format_time)
            df_today["exit_time"] = df_today["exit_time"].apply(format_time) if "exit_time" in df_today else None
            df_today["roi"] = df_today.apply(lambda row: calculate_roi(row["entry_price"], row["exit_price"]), axis=1)
            df_today["holding_time"] = df_today.apply(lambda row: calculate_holding(row["entry_time"], row["exit_time"]), axis=1)
            df_today["exit_or_skip_reason"] = df_today["exit_reason"].fillna("") + df_today["skip_reason"].fillna("")
            df_today = df_today[["ticker", "headline", "sentiment", "sentiment_score",
                                 "entry_amount", "entry_price", "entry_time",
                                 "exit_price", "exit_time", "roi", "holding_time", "exit_or_skip_reason"]]
            st.dataframe(df_today, use_container_width=True)
        else:
            st.info("No skipped or closed trades today.")
    except Exception as e:
        st.warning(f"Error loading today's skipped/closed trades: {e}")

with tab3:
    st.subheader("📁 Skipped / Closed Trades (Previous)")
    try:
        df_prev = pd.read_sql_query("""
            SELECT * FROM trades
            WHERE (exit_price IS NOT NULL OR skip_reason IS NOT NULL)
              AND DATE(COALESCE(exit_time, entry_time)) < DATE('now')
            ORDER BY COALESCE(exit_time, entry_time) DESC
        """, conn)
        if not df_prev.empty:
            df_prev["entry_time"] = df_prev["entry_time"].apply(format_time)
            df_prev["exit_time"] = df_prev["exit_time"].apply(format_time) if "exit_time" in df_prev else None
            df_prev["roi"] = df_prev.apply(lambda row: calculate_roi(row["entry_price"], row["exit_price"]), axis=1)
            df_prev["holding_time"] = df_prev.apply(lambda row: calculate_holding(row["entry_time"], row["exit_time"]), axis=1)
            df_prev["exit_or_skip_reason"] = df_prev["exit_reason"].fillna("") + df_prev["skip_reason"].fillna("")
            df_prev = df_prev[["ticker", "headline", "sentiment", "sentiment_score",
                               "entry_amount", "entry_price", "entry_time",
                               "exit_price", "exit_time", "roi", "holding_time", "exit_or_skip_reason"]]
            st.dataframe(df_prev, use_container_width=True)
        else:
            st.info("No older skipped or closed trades.")
    except Exception as e:
        st.warning(f"Error loading previous skipped/closed trades: {e}")

with tab4:
    st.subheader("📉 Run Backtest")
    from_date = st.date_input("From Date", value=datetime.today() - timedelta(days=7))
    to_date = st.date_input("To Date", value=datetime.today())
    if st.button("Run Backtest"):
        os.system(f"python3 backtest_runner.py '{from_date}' '{to_date}'")
        st.success("Backtest started...")

conn.close()
