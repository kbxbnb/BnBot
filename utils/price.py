import os, time
import pandas as pd
import requests

def get_alpaca_keys():
    api = os.getenv("ALPACA_API_KEY") or ""
    secret = os.getenv("ALPACA_SECRET_KEY") or ""
    return api, secret

def fetch_intraday_bars(ticker: str, start_iso: str | None = None, timeframe: str = "5Min", limit: int = 300) -> pd.DataFrame | None:
    """Fetch intraday bars from Alpaca Market Data v2 (Stocks)."""
    api, secret = get_alpaca_keys()
    if not api or not secret:
        return None
    base = "https://data.alpaca.markets/v2/stocks/bars"
    params = {"symbols": ticker.upper(), "timeframe": timeframe, "limit": limit}
    if start_iso: params["start"] = start_iso
    headers = {"APCA-API-KEY-ID": api, "APCA-API-SECRET-KEY": secret}
    r = requests.get(base, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if "bars" not in data: return None
    bars = data["bars"].get(ticker.upper(), [])
    if not bars: return None
    df = pd.DataFrame(bars)
    if df.empty: return None
    # Expected columns: t (time), o,h,l,c,v, etc.
    df["t"] = pd.to_datetime(df["t"])
    df.rename(columns={"t":"time","o":"open","h":"high","l":"low","c":"close","v":"volume"}, inplace=True)
    df.sort_values("time", inplace=True)
    return df

def calc_vwap(df: pd.DataFrame) -> pd.Series:
    pv = (df["close"] * df["volume"]).cumsum()
    vv = df["volume"].cumsum()
    return pv / vv

def calc_rvol(df: pd.DataFrame, window: int = 30) -> float:
    """Relative volume = current bar volume / average volume of prior N bars."""
    if len(df) < window + 1: return 1.0
    avg = df["volume"].iloc[-(window+1):-1].mean()
    if avg == 0: return 1.0
    return df["volume"].iloc[-1] / avg

def breaks_recent_resistance(df: pd.DataFrame, lookback: int = 20) -> bool:
    recent_high = df["high"].iloc[-lookback:-1].max() if len(df) > lookback else df["high"].max()
    return df["close"].iloc[-1] > recent_high
