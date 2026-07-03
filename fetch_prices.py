"""
fetch_prices.py -- refresh daily OHLC from Twelve Data.

Why not yfinance? Yahoo rate-limits (HTTP 429) and stopped serving fresh bars.
Twelve Data's free tier (8 req/min, 800/day) serves clean daily bars including
the current session, so we use it for the analysis window.

Each symbol is written to daily_<SYM>.csv with the same schema the old yfinance
dump used (Date, Adj Close, Close, High, Low, Open, Volume, Ticker) so existing
tooling keeps working. Long Yahoo history before the Twelve Data window is
preserved; the recent window is overwritten with Twelve Data bars so the
analysis period comes from one consistent source.

Usage:
    python fetch_prices.py                 # CORE_SYMBOLS (SPY QQQ IWM DIA)
    python fetch_prices.py --all           # full ALL_SYMBOLS universe
    python fetch_prices.py SPY QQQ         # specific symbols
    python fetch_prices.py --outputsize 500
"""
import argparse
import sys
import time

import pandas as pd
import requests

import config

TD = "https://api.twelvedata.com/time_series"
COLUMNS = ["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume", "Ticker"]


def fetch_symbol(sym, outputsize):
    params = dict(symbol=sym, interval="1day", outputsize=outputsize,
                  order="ASC", apikey=config.TWELVE_DATA_API_KEY)
    r = requests.get(TD, params=params, timeout=25)
    js = r.json()
    if js.get("status") == "error" or "values" not in js:
        raise RuntimeError(js.get("message", str(js)[:200]))
    df = pd.DataFrame(js["values"])
    df = df.rename(columns={"datetime": "Date", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"})
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Adj Close"] = df["Close"]      # TD daily close is already split-adjusted
    df["Ticker"] = sym
    return df[COLUMNS]


def merge_into_csv(sym, fresh):
    """Keep old history before the fresh window, then append fresh bars."""
    path = config.PRICE_DIR / f"daily_{sym}.csv"
    if path.exists():
        old = pd.read_csv(path)
        old["Date"] = old["Date"].astype(str).str[:10]
        cutoff = fresh["Date"].min()
        kept = old[old["Date"] < cutoff]
        out = pd.concat([kept, fresh], ignore_index=True)
    else:
        out = fresh
    out = out.drop_duplicates(subset="Date", keep="last").sort_values("Date")
    out.to_csv(path, index=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="symbols (default: CORE_SYMBOLS)")
    ap.add_argument("--all", action="store_true", help="refresh full universe")
    ap.add_argument("--outputsize", type=int, default=400,
                    help="daily bars to pull (400 ~= 1.5y)")
    ap.add_argument("--sleep", type=float, default=8.0,
                    help="seconds between calls (free tier = 8 req/min)")
    args = ap.parse_args()

    if not config.TWELVE_DATA_API_KEY:
        sys.exit("No TWELVE_DATA_API_KEY in .env")

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    elif args.all:
        symbols = config.ALL_SYMBOLS
    else:
        symbols = config.CORE_SYMBOLS

    print(f"Refreshing {len(symbols)} symbol(s) from Twelve Data "
          f"(outputsize={args.outputsize})")
    ok, fail = 0, 0
    for i, sym in enumerate(symbols):
        try:
            fresh = fetch_symbol(sym, args.outputsize)
            out = merge_into_csv(sym, fresh)
            last = out.iloc[-1]
            print(f"  {sym:5s} -> {len(out):5d} rows, latest {last['Date']} "
                  f"close {last['Close']:.2f}")
            ok += 1
        except (RuntimeError, requests.RequestException) as e:
            print(f"  {sym:5s} ! {e}", file=sys.stderr)
            fail += 1
        if i < len(symbols) - 1:
            time.sleep(args.sleep)   # stay under the free-tier rate limit

    print(f"Done: {ok} ok, {fail} failed")


if __name__ == "__main__":
    main()
