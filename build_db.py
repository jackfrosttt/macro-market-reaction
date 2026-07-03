"""
build_db.py -- load everything into a local SQLite database (market.db).

One file on your disk you can query with plain SQL (or DB Browser for SQLite,
https://sqlitebrowser.org). Tables:

  prices           daily OHLC for every daily_<SYM>.csv
  macro_releases   the FRED macro calendar with actual values + release TIME
  event_reactions  one row per (macro release day x report): SPY/QQQ reaction,
                   the release time, and the DIRECTIONAL/CHOP class
  intraday         30-min bars for SPY/QQQ (only if you've run fetch_intraday.py)

Usage:
    python build_db.py                 # (re)build from the CSVs on disk
    python run.py db                   # same thing

Then, e.g.:
    sqlite3 market.db "SELECT * FROM event_reactions WHERE spy_class='DIRECTIONAL';"
"""
import glob
import sqlite3

import pandas as pd

import config
from analyze import load_prices, classify, load_events

DB = config.ROOT / "market.db"


def load_all_prices():
    frames = []
    for path in sorted(glob.glob(str(config.PRICE_DIR / "daily_*.csv"))):
        if path.endswith("daily_ALL.csv"):
            continue
        df = pd.read_csv(path)
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        df["date"] = df["date"].astype(str).str[:10]
        frames.append(df)
    allp = pd.concat(frames, ignore_index=True)
    keep = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
    return allp[[c for c in keep if c in allp.columns]]


def build_event_reactions():
    """Join each macro release date to SPY & QQQ reaction + class + time."""
    spy = load_prices("SPY").set_index("Date")
    qqq = load_prices("QQQ").set_index("Date")
    m = load_events()   # FRED + supplemental (ISM etc.), incl. consensus/surprise
    rows = []
    for _, r in m.iterrows():
        d = r["Date"]
        if d not in spy.index:
            continue
        s = spy.loc[d]
        q = qqq.loc[d] if d in qqq.index else None
        rows.append({
            "date": d.date().isoformat(),
            "report": r["report"],
            "tier": r["tier"],
            "time_et": r.get("time_et"),
            "value": r.get("value"),
            "chg_vs_prev": r.get("chg_vs_prev"),
            "consensus": r.get("consensus"),
            "surprise": r.get("surprise"),
            "source": r.get("source"),
            "spy_gap": round(float(s["gap"]), 5),
            "spy_ret_cc": round(float(s["ret_cc"]), 5),
            "spy_ret_oc": round(float(s["ret_oc"]), 5),
            "spy_range": round(float(s["range_pct"]), 5),
            "spy_close_loc": round(float(s["close_loc"]), 4),
            "spy_trend_eff": round(float(s["trend_eff"]), 4),
            "spy_class": classify(s),
            "qqq_ret_cc": round(float(q["ret_cc"]), 5) if q is not None else None,
            "qqq_trend_eff": round(float(q["trend_eff"]), 4) if q is not None else None,
        })
    return pd.DataFrame(rows)


def main():
    con = sqlite3.connect(DB)
    prices = load_all_prices()
    prices.to_sql("prices", con, if_exists="replace", index=False)

    macro = pd.read_csv(config.MACRO_CSV)
    macro.to_sql("macro_releases", con, if_exists="replace", index=False)

    ev = build_event_reactions()
    ev.to_sql("event_reactions", con, if_exists="replace", index=False)

    # helpful indexes
    cur = con.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS ix_prices ON prices(ticker, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_evt ON event_reactions(date, report)")
    con.commit()

    print(f"Built {DB}")
    for t in ["prices", "macro_releases", "event_reactions"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {n:6d} rows")
    if con.execute("SELECT name FROM sqlite_master WHERE name='intraday'").fetchone():
        n = con.execute("SELECT COUNT(*) FROM intraday").fetchone()[0]
        print(f"  {'intraday':16s} {n:6d} rows")
    con.close()


if __name__ == "__main__":
    main()
