# logs_tab.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import streamlit as st
import pytz
from datetime import timezone
import importlib

PT = pytz.timezone("US/Pacific")


def render(conn):
    """Render the Logs tab: auto-refresh, poller health, latest API calls, DB status, and debug actions."""

    # --- Auto-refresh (user-controlled) ---
    colA, colB = st.columns([1, 2])
    enable_auto = colA.checkbox("Auto-refresh", value=True, help="Refresh this Logs tab periodically")
    interval_sec = colB.slider("Interval (seconds)", 10, 120, 30, 5)
    if enable_auto and hasattr(st, "autorefresh"):
        st.autorefresh(interval=interval_sec * 1000, key="logs_refresh")

    # --- Poller health (green if last RESPONSE ≤ 90s ago)
    try:
        q = """
          SELECT timestamp
          FROM logs
          WHERE component='benzinga' AND event='RESPONSE'
          ORDER BY id DESC
          LIMIT 1
        """
        df = pd.read_sql(q, conn)
        if df.empty:
            ok, msg = False, "no responses yet"
        else:
            last = pd.to_datetime(df["timestamp"].iloc[0], utc=True)
            age = (pd.Timestamp.now(tz=timezone.utc) - last).total_seconds()
            ok, msg = (age <= 90), f"last response {int(age)}s ago"
        st.markdown(f"**Poller status:** {'🟢 Healthy' if ok else '🔴 Stale'} — {msg}")
    except Exception as e:
        st.info(f"Poller status unavailable: {e}")

    # --- Latest Benzinga API Calls (top block)
    st.subheader("Latest Benzinga API Calls")
    try:
        q_calls = """
          SELECT timestamp, event, message
          FROM logs
          WHERE component='benzinga'
          ORDER BY id DESC
          LIMIT 10
        """
        df_calls = pd.read_sql(q_calls, conn)
        if df_calls.empty:
            st.info("No recent Benzinga API activity logged.")
        else:
            ts = pd.to_datetime(df_calls["timestamp"], utc=True, errors="coerce").dt.tz_convert(PT)
            df_calls = df_calls.assign(**{"Time (PT)": ts}).drop(columns=["timestamp"])
            df_calls = df_calls.rename(columns={"event": "Event", "message": "Details"})
            st.dataframe(df_calls[["Time (PT)", "Event", "Details"]], use_container_width=True, height=260)
    except Exception as e:
        st.warning(f"Error loading Benzinga API logs: {e}")

    # --- DB Status (row counts)
    try:
        def _count(sql):
            try:
                return pd.read_sql(sql, conn).iloc[0, 0]
            except Exception:
                return 0

        news_cnt     = _count("SELECT COUNT(*) AS n FROM news")
        logs_cnt     = _count("SELECT COUNT(*) AS n FROM logs")
        open_cnt     = _count("SELECT COUNT(*) AS n FROM trades WHERE exit_price IS NULL AND skip_reason IS NULL")
        closed_cnt   = _count("SELECT COUNT(*) AS n FROM trades WHERE exit_price IS NOT NULL")
        skipped_cnt  = _count("SELECT COUNT(*) AS n FROM trades WHERE skip_reason IS NOT NULL")

        st.markdown(
            f"**DB Status:** "
            f"📰 news: `{news_cnt}` • "
            f"🧾 logs: `{logs_cnt}` • "
            f"📈 open trades: `{open_cnt}` • "
            f"✅ closed: `{closed_cnt}` • "
            f"⛔ skipped: `{skipped_cnt}`"
        )
    except Exception as e:
        st.info(f"DB status unavailable: {e}")

    st.markdown("---")

    # --- Manual one-poll trigger
    with st.expander("🔍 Debug: Manually run one Benzinga poll"):
        st.caption("Executes a single request via `news_fetcher.fetch_and_log_once()` and logs REQUEST/RESPONSE.")
        if st.button("Run one poll now"):
            try:
                news_fetcher = importlib.import_module("news_fetcher")
                with st.spinner("Contacting Benzinga…"):
                    news_fetcher.fetch_and_log_once()
                st.success("✅ Poll completed. The table above will reflect the latest REQUEST/RESPONSE.")
                st.rerun()
            except Exception as e:
                st.error(f"Poll failed: {e}")

    # --- Inspect parsed sample + ingest breakdown
    with st.expander("🧪 Debug: Inspect parsed sample & ingest breakdown", expanded=False):
        c1, c2 = st.columns(2)

        # Last parsed sample
        try:
            df_ps = pd.read_sql("""
                SELECT timestamp, message
                FROM logs
                WHERE component='benzinga' AND event='PARSED_SAMPLE'
                ORDER BY id DESC
                LIMIT 1
            """, conn)
            if df_ps.empty:
                c1.info("No PARSED_SAMPLE yet. Run the poller or click 'Run one poll now'.")
            else:
                c1.markdown("**Last PARSED_SAMPLE:**")
                c1.code(df_ps["message"].iloc[0], language="json")
        except Exception as e:
            c1.warning(f"PARSED_SAMPLE load error: {e}")

        # Ingest breakdown
        try:
            df_br = pd.read_sql("""
                SELECT timestamp, message
                FROM logs
                WHERE component='benzinga' AND event='INGEST_SUMMARY_DETAILED'
                ORDER BY id DESC
                LIMIT 1
            """, conn)
            if df_br.empty:
                c2.info("No INGEST_SUMMARY_DETAILED yet.")
            else:
                c2.markdown("**Last INGEST_SUMMARY_DETAILED:**")
                c2.code(df_br["message"].iloc[0], language="json")
        except Exception as e:
            c2.warning(f"Ingest summary load error: {e}")

        st.markdown("---")
        # Last 5 news rows
        try:
            df_last_news = pd.read_sql("""
                SELECT ticker, headline, news_time
                FROM news
                ORDER BY id DESC
                LIMIT 5
            """, conn)
            if df_last_news.empty:
                st.info("news table is empty.")
            else:
                st.markdown("**Latest news rows (top 5):**")
                st.dataframe(df_last_news, use_container_width=True, height=180)
        except Exception as e:
            st.warning(f"Could not load news preview: {e}")