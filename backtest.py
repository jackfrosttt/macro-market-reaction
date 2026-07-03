"""
backtest.py -- do the patterns actually make money? Test rules, don't trust vibes.

Rules tested on SPY (long history from daily bars; intraday rules on the ~1.5y
of 30-min data). All results are BEFORE commissions/slippage and use index
moves as a stand-in for what a directional option would ride.

  A. GAP-FOLLOW on event days     buy the open in the gap's direction, exit close
  B. GAP-FADE on event days       the opposite
  C. MORNING-TREND on macro days  at 11:30 go in the direction of open->11:30,
                                  exit at close (the +0.21 trend pattern)
  D. same rule on QUIET days      (should LOSE if the fade pattern is real)
  E. ISM-day check                1st + 3rd business day of month ~10am (ISM Mfg
                                  / Services release days) -- are they directional?

Usage:  python run.py backtest
"""
import datetime as dt
import sqlite3

import numpy as np
import pandas as pd

import config
from analyze import load_prices, load_events, classify

DB = config.ROOT / "market.db"


def eq_line(rets):
    r = pd.Series(rets).dropna()
    if not len(r):
        return "n=0"
    win = (r > 0).mean()
    avg = r.mean()
    total = r.sum()
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() else float("nan")
    return (f"n={len(r):3d}  win {win*100:3.0f}%  avg {avg*100:+.2f}%/trade  "
            f"total {total*100:+.1f}%  ann.Sharpe {sharpe:+.1f}")


def daily_rules():
    spy = load_prices("SPY")
    ev = load_events()
    ev = ev[ev["tier"] <= 2]
    event_dates = set(ev["Date"])
    d = spy[(spy["Date"] >= "2024-01-01")].copy()
    d["is_event"] = d["Date"].isin(event_dates)
    d = d.dropna(subset=["gap", "ret_oc"])

    e = d[d["is_event"] & (d["gap"].abs() > 0.001)]
    q = d[~d["is_event"] & (d["gap"].abs() > 0.001)]
    print("[A] GAP-FOLLOW  (event days, |gap|>0.1%): enter open w/ gap, exit close")
    print("    event days :", eq_line(np.sign(e["gap"]) * e["ret_oc"]))
    print("    quiet days :", eq_line(np.sign(q["gap"]) * q["ret_oc"]))
    print("[B] GAP-FADE   (same days, opposite direction)")
    print("    event days :", eq_line(-np.sign(e["gap"]) * e["ret_oc"]))
    print("    quiet days :", eq_line(-np.sign(q["gap"]) * q["ret_oc"]))

    # per-tier1 report gap-follow
    print("\n    gap-follow by report (tier 1 only):")
    spy_ix = spy.set_index("Date")
    for rep in ["Jobs Report (NFP + Unemployment)", "CPI (Consumer Price Index)",
                "FOMC Rate Decision", "PCE (Personal Income & Outlays)"]:
        dd = spy_ix.reindex(ev[ev["report"] == rep]["Date"].unique()).dropna(subset=["gap"])
        dd = dd[dd["gap"].abs() > 0.001]
        print(f"      {rep[:30]:32s}", eq_line(np.sign(dd["gap"]) * dd["ret_oc"]))
    return d


def intraday_rules():
    con = sqlite3.connect(DB)
    bars = pd.read_sql("SELECT * FROM intraday WHERE ticker='SPY'", con)
    con.close()
    bars["dt"] = pd.to_datetime(bars["dt"])
    bars["day"] = bars["dt"].dt.date.astype(str)
    bars["time"] = bars["dt"].dt.strftime("%H:%M")
    ev = load_events()
    event_days = set(ev[ev["tier"] <= 2]["Date"].dt.date.astype(str))

    rows = []
    for day, g in bars.groupby("day"):
        g = g.sort_values("dt")
        o = float(g["open"].iloc[0]); c = float(g["close"].iloc[-1])
        h1130 = g[g["time"] == "11:30"]
        if h1130.empty:
            continue
        p1130 = float(h1130["close"].iloc[0])
        rows.append({"day": day, "macro": day in event_days,
                     "morning": p1130 / o - 1, "rest": c / p1130 - 1})
    r = pd.DataFrame(rows)
    r = r[r["morning"].abs() > 0.002]      # need a real morning move to act on
    mac, qui = r[r["macro"]], r[~r["macro"]]
    print("\n[C] MORNING-TREND on MACRO days (|open->11:30| > 0.2%):")
    print("    follow morning:", eq_line(np.sign(mac["morning"]) * mac["rest"]))
    print("[D] same rule on QUIET days (expect worse if fade pattern is real):")
    print("    follow morning:", eq_line(np.sign(qui["morning"]) * qui["rest"]))
    print("    fade morning  :", eq_line(-np.sign(qui["morning"]) * qui["rest"]))


def ism_days():
    """ISM Mfg = 1st business day of month, ISM Services = 3rd. ~10am ET.
    We don't have ISM values (not on FRED), but we CAN measure how those days
    trade -- which answers 'is ISM day directional?' from price evidence."""
    spy = load_prices("SPY").set_index("Date")
    idx = spy.index[spy.index >= "2024-01-01"]
    months = sorted({(d.year, d.month) for d in idx})
    d1, d3 = [], []
    for y, m in months:
        bd = [d for d in idx if d.year == y and d.month == m]
        if len(bd) >= 3:
            d1.append(bd[0]); d3.append(bd[2])
    out = []
    for label, days in [("ISM Mfg day (1st bday)", d1), ("ISM Svcs day (3rd bday)", d3)]:
        dd = spy.loc[[d for d in days if d in spy.index]].dropna(subset=["ret_cc"])
        kl = dd.apply(classify, axis=1)
        out.append((label, len(dd), dd["ret_cc"].abs().mean(),
                    dd["trend_eff"].mean(), (kl == "DIRECTIONAL").mean()))
    base = spy.loc[idx].dropna(subset=["ret_cc"])
    kb = base.apply(classify, axis=1)
    out.append(("ALL days (baseline)", len(base), base["ret_cc"].abs().mean(),
                base["trend_eff"].mean(), (kb == "DIRECTIONAL").mean()))
    print("\n[E] ARE ISM DAYS DIRECTIONAL?  (proxy: 1st/3rd business day, 2.5y)")
    print(f"    {'':26s}{'n':>4s}{'avg|move|':>10s}{'trend':>7s}{'dir%':>6s}")
    for label, n, mv, tr, dr in out:
        print(f"    {label:26s}{n:4d}{mv*100:9.2f}%{tr:7.2f}{dr*100:5.0f}%")


def main():
    print("=" * 74)
    print(" BACKTEST  |  SPY  |  2024-01-01 -> today  (daily) + ~1.5y intraday")
    print(" NOTE: index moves, no costs. A directional option multiplies these")
    print(" several-fold but adds theta/IV risk. Compare RULES, not absolute P&L.")
    print("=" * 74)
    daily_rules()
    intraday_rules()
    ism_days()


if __name__ == "__main__":
    main()
