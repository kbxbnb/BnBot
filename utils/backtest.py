import os, json, math, time, requests
import pandas as pd
from datetime import datetime, timezone
from dateutil import parser
from .sentiment import score_sentiment
from .price import fetch_intraday_bars, calc_vwap, calc_rvol, breaks_recent_resistance

BENZINGA_API_KEY = (
    os.getenv("BENZINGA_API_KEY")
    or os.getenv("BENZINGA__API_KEY")
    or "YOUR_BENZINGA_API_KEY"
)

def fetch_benzinga_news_range(start_iso: str, end_iso: str, tickers: list[str] | None = None, pagesize: int = 100) -> list[dict]:
    """Fetch Benzinga news within [start,end]. Returns list of articles with title, created, stocks."""
    url = "https://api.benzinga.com/api/v2/news"
    params = {
        "token": BENZINGA_API_KEY,
        "pagesize": pagesize,
        "display_tickers": "true",
        "date": f"{start_iso},{end_iso}",
        # optional: "channels": "general"
    }
    if tickers:
        params["tickers"] = ",".join([t.upper() for t in tickers])
    out = []
    page = 0
    while True:
        p = params.copy()
        if page > 0:
            p["page"] = page
        r = requests.get(url, params=p, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        # normalize
        articles = data.get("articles") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not articles:
            break
        out.extend(articles)
        if len(articles) < pagesize:
            break
        page += 1
        if page > 50:  # safety cap
            break
    return out

def simulate_for_news(articles: list[dict], rvol_threshold: float = 1.5, timeframe: str = "5Min"):
    """Simulate entries using same rules against Alpaca bars around news timestamps.
    Returns a DataFrame of simulated trades with ROI and reason when skipped.
    """
    rows = []
    for a in articles:
        headline = a.get("title") or a.get("headline") or ""
        created = a.get("created") or a.get("published") or a.get("time") or ""
        stocks = a.get("stocks") or a.get("tickers") or []
        if not headline or not created or not stocks:
            continue
        # sentiment (prefer benzinga tag)
        label, score, source = score_sentiment(headline, {"sentiment": a.get("sentiment")} if a.get("sentiment") else None)

        for t in stocks:
            ticker = (t or "").upper().strip()
            if not ticker:
                continue
            # Fetch bars (last day window around news)
            df = fetch_intraday_bars(ticker, timeframe=timeframe, limit=240)
            if df is None or df.empty:
                rows.append(dict(ticker=ticker, headline=headline, sentiment=label, sentiment_score=score,
                                 sentiment_source=source, entry_price=None, exit_price=None, roi=None,
                                 result="skipped", reason="No price data"))
                continue
            # Entry rules
            vwap = calc_vwap(df).iloc[-1]
            rvol = calc_rvol(df, window=30)
            resistance = breaks_recent_resistance(df, lookback=20)
            above_vwap = df["close"].iloc[-1] > vwap
            if not (label in ("bullish","very bullish") and above_vwap and rvol > rvol_threshold and resistance):
                rows.append(dict(ticker=ticker, headline=headline, sentiment=label, sentiment_score=score,
                                 sentiment_source=source, entry_price=None, exit_price=None, roi=None,
                                 result="skipped", reason="Rules not met"))
                continue
            # Simulate entry at last close and simple TSL 10% then flat exit after 20 bars
            entry = float(df["close"].iloc[-1])
            peak = entry
            exit_px = None
            for i in range(1, min(20, len(df))):
                px = float(df["close"].iloc[-i])
                peak = max(peak, px)
                if (peak - px) / peak >= 0.10:  # 10% TSL
                    exit_px = px
                    reason = "TSL 10%"
                    break
            if exit_px is None:
                exit_px = float(df["close"].iloc[-1])
                reason = "Timed exit"
            r = round((exit_px - entry) / entry * 100.0, 2) if entry else None
            rows.append(dict(ticker=ticker, headline=headline, sentiment=label, sentiment_score=score,
                             sentiment_source=source, entry_price=entry, exit_price=exit_px, roi=r,
                             result="closed", reason=reason))
    return pd.DataFrame(rows)

def summarize(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "avg_roi": 0.0, "total_pnl": 0.0, "max_drawdown": 0.0}
    closed = df[df["result"]=="closed"].copy()
    wins = (closed["roi"] > 0).sum() if "roi" in closed else 0
    trades = len(closed)
    win_rate = round((wins / trades * 100.0), 2) if trades else 0.0
    avg_roi = round(closed["roi"].mean(), 2) if trades else 0.0
    total_pnl = round((closed["exit_price"] - closed["entry_price"]).sum(), 2) if trades else 0.0
    # crude drawdown approximation
    max_drawdown = 0.0
    if trades:
        eq = (closed["exit_price"] - closed["entry_price"]).cumsum()
        peak = 0.0
        for v in eq:
            peak = max(peak, v)
            dd = (peak - v)
            max_drawdown = max(max_drawdown, dd)
    return {"trades": trades, "wins": int(wins), "win_rate": win_rate, "avg_roi": avg_roi,
            "total_pnl": total_pnl, "max_drawdown": round(max_drawdown, 2)}
