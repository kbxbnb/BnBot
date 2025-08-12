import sys, os, json
from datetime import datetime, timezone
import pandas as pd
from utils.backtest import fetch_benzinga_news_range, simulate_for_news, summarize

def usage():
    print("Usage: python backtest_runner.py YYYY-MM-DD YYYY-MM-DD [TICKERS_COMMA_SEP] [RVOL_THRESHOLD]")
    sys.exit(1)

def main():
    if len(sys.argv) < 3:
        usage()
    start = sys.argv[1]
    end   = sys.argv[2]
    tickers = None
    rvol_threshold = 1.5
    if len(sys.argv) >= 4 and sys.argv[3].strip():
        tickers = [t.strip().upper() for t in sys.argv[3].split(",")]
    if len(sys.argv) >= 5 and sys.argv[4].strip():
        try:
            rvol_threshold = float(sys.argv[4])
        except:
            pass

    # convert to ISO (inclusive day range)
    start_iso = f"{start}T00:00:00Z"
    end_iso   = f"{end}T23:59:59Z"

    print(f"Fetching Benzinga news {start} → {end} ...")
    arts = fetch_benzinga_news_range(start_iso, end_iso, tickers=tickers)
    print(f"Got {len(arts)} headlines. Simulating ...")

    df = simulate_for_news(arts, rvol_threshold=rvol_threshold)
    os.makedirs("data", exist_ok=True)
    csv_path = f"data/backtest_{start}_{end}.csv"
    df.to_csv(csv_path, index=False)

    summary = summarize(df)
    json_path = f"data/backtest_{start}_{end}_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("Summary:", summary)
    print("Saved:", csv_path, json_path)

if __name__ == "__main__":
    main()
