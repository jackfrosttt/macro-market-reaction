"""
fetch_intraday.py -- 30-minute bars so we can see WHEN the move happened.

Daily bars can't tell you if a report at 10:00am or 2:00pm caused the move.
This pulls 30-min bars for SPY/QQQ from Twelve Data into market.db and builds an
`event_intraday` table that, for each macro-release day, measures the reaction in
the window around the report's release time.

Reaction windows by release time:
  08:30 reports -> the market is closed at 8:30, so the reaction shows up as the
                   OPEN GAP (prior close -> 9:30 open) plus the first 30 min.
  10:00 reports -> move from the 09:30-10:00 bar into the 10:00-10:30 reaction.
  14:00 reports -> move from the 13:30 level into the 4:00pm close (FOMC style).

Usage:
    python fetch_intraday.py                 # SPY + QQQ, ~115 trading days
    python fetch_intraday.py --outputsize 3000
"""
import argparse
import sqlite3
import sys

import pandas as pd
import requests

import config
from analyze import classify, load_prices

DB = config.ROOT / "market.db"
TD = "https://api.twelvedata.com/time_series"


def fetch(sym, outputsize):
    r = requests.get(TD, timeout=30, params=dict(
        symbol=sym, interval="30min", outputsize=outputsize, order="ASC",
        apikey=config.TWELVE_DATA_API_KEY))
    js = r.json()
    if "values" not in js:
        raise RuntimeError(js.get("message", str(js)[:200]))
    df = pd.DataFrame(js["values"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ticker"] = sym
    df = df.rename(columns={"datetime": "dt"})
    return df[["ticker", "dt", "open", "high", "low", "close", "volume"]]


def bar_at(day_bars, hhmm):
    """close of the 30-min bar starting at hh:mm, or None."""
    hit = day_bars[day_bars["time"] == hhmm]
    return float(hit["close"].iloc[0]) if len(hit) else None


def build_event_intraday(intraday):
    """For each macro release day, measure the reaction in the report's window."""
    intraday["dt"] = pd.to_datetime(intraday["dt"])
    intraday["day"] = intraday["dt"].dt.date.astype(str)
    intraday["time"] = intraday["dt"].dt.strftime("%H:%M")
    spy_daily = load_prices("SPY").set_index("Date")

    m = pd.read_csv(config.MACRO_CSV)
    m["Date"] = pd.to_datetime(m["release_date"])
    rows = []
    for _, r in m.iterrows():
        day = r["Date"].date().isoformat()
        at = str(r.get("time_et", ""))
        for sym in ["SPY", "QQQ"]:
            db = intraday[(intraday["ticker"] == sym) & (intraday["day"] == day)]
            if db.empty:
                continue
            db = db.sort_values("dt")
            open_ = float(db["open"].iloc[0])       # 9:30 open
            close_ = float(db["close"].iloc[-1])    # 4:00 close
            # define the reaction window per release time
            if at.startswith("08:30"):
                win_from, win_to, note = None, "10:00", "open-gap + first 30m"
            elif at.startswith("10:00"):
                win_from, win_to, note = "09:30", "10:30", "10:00 print"
            elif at.startswith("14:00"):
                win_from, win_to, note = "13:30", "15:30", "2:00 -> close"
            else:
                win_from, win_to, note = "09:30", "15:30", "full session"
            p0 = bar_at(db, win_from) if win_from else \
                (spy_daily.loc[r["Date"], "gap"] if sym == "SPY" else None)
            p1 = bar_at(db, win_to)
            # reaction move over the window (or the open gap for 8:30)
            if win_from is None:
                # 8:30 report: reaction = overnight gap into the open
                pc = float(db["open"].iloc[0])
                react = None  # gap captured separately in daily table
                window_move = (bar_at(db, "10:00") / open_ - 1) if bar_at(db, "10:00") else None
            else:
                window_move = (p1 / p0 - 1) if (p0 and p1) else None
            rows.append({
                "date": day, "report": r["report"], "time_et": at,
                "ticker": sym, "window": note,
                "open_930": round(open_, 2), "close_1600": round(close_, 2),
                "window_move": round(window_move, 5) if window_move is not None else None,
                "day_move": round(close_ / open_ - 1, 5),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputsize", type=int, default=1500)  # ~115 trading days
    args = ap.parse_args()
    if not config.TWELVE_DATA_API_KEY:
        sys.exit("No TWELVE_DATA_API_KEY in .env")

    frames = []
    for sym in ["SPY", "QQQ"]:
        print(f"Fetching 30-min bars for {sym} ...")
        frames.append(fetch(sym, args.outputsize))
    intraday = pd.concat(frames, ignore_index=True)

    con = sqlite3.connect(DB)
    intraday.to_sql("intraday", con, if_exists="replace", index=False)
    ev = build_event_intraday(intraday)
    ev.to_sql("event_intraday", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS ix_intr ON intraday(ticker, dt)")
    con.commit()
    print(f"Stored {len(intraday)} intraday bars + {len(ev)} event-intraday rows in {DB}")
    con.close()


if __name__ == "__main__":
    main()
