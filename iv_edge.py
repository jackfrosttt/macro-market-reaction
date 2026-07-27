#!/usr/bin/env python3
"""
iv_edge.py -- is the option CHEAP relative to how much the stock actually moves?

Movement alone doesn't make money: you pay implied vol to get realized vol.
So for each candidate we compare what the option charges vs what the stock does.

  iv_atm     ATM implied vol, nearest expiry 7-45 DTE (CBOE, ~15min delayed)
  rv21/rv10  realized annualized vol, last 21 / 10 complete sessions
  vrp        rv21 - iv_atm.  POSITIVE = stock is moving MORE than options
             charge -> favors BUYING premium. NEGATIVE = you're overpaying
             -> favors SELLING premium (spreads, condors).
  imp10d     the 1-sigma move options price over a 10-day hold = iv/sqrt(252)*sqrt(10)
  mfe10r     median best-case 10d capture actually realized in this regime
  ratio      mfe10r / imp10d.  >1.3 = the realized swing has been comfortably
             bigger than the premium being charged.

CAVEAT: mfe10r is a BEST-case-within-window number (perfect exit), while imp10d
is a 1-sigma terminal move. `ratio` therefore flatters the buyer -- treat it as
a screen, not an expectancy. `vrp` is the clean, apples-to-apples signal.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_options import fetch_chain                      # noqa: E402
from rotation_scan import load, split_partial, mfe_stats   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent

CANDIDATES = ["USO", "XLE", "AAPL", "SPCX", "MU", "AMD", "SOXL", "TSLA",
              "CRWD", "NVDA", "SMH", "META", "MSFT", "GOOGL", "AMZN",
              "QQQ", "SPY", "IWM"]


def atm_iv(df, spot):
    d = df.copy()
    d["dte"] = (pd.to_datetime(d["expiry"]).dt.date
                - pd.Timestamp.today().date()).apply(lambda x: x.days)
    near = d[(d["dte"] >= 7) & (d["dte"] <= 45)]
    if not len(near):
        return np.nan, np.nan
    exp = near.sort_values("dte")["expiry"].iloc[0]
    e = near[near["expiry"] == exp]
    atm = e.iloc[(e["strike"] - spot).abs().argsort()[:6]]
    ivs = pd.to_numeric(atm["iv"], errors="coerce")
    ivs = ivs[ivs > 0]
    dte = int(e["dte"].iloc[0])
    return (float(ivs.mean()) * 100 if len(ivs) else np.nan), dte


def realized(sym):
    df = load(ROOT / f"daily_{sym}.csv")
    df, _ = split_partial(df)
    r = df["Close"].pct_change().dropna()
    rv21 = float(r.tail(21).std() * np.sqrt(252) * 100)
    rv10 = float(r.tail(10).std() * np.sqrt(252) * 100)
    mfe, p5 = mfe_stats(df["Close"].tail(32))
    return rv21, rv10, mfe, p5, float(df["Close"].iloc[-1])


def main():
    rows = []
    for sym in CANDIDATES:
        try:
            chain, spot = fetch_chain(sym)
            iv, dte = atm_iv(chain, spot)
        except Exception as e:
            print(f"  ! {sym}: chain fetch failed ({e})", file=sys.stderr)
            iv, dte, spot = np.nan, np.nan, np.nan
        try:
            rv21, rv10, mfe, p5, last = realized(sym)
        except Exception as e:
            print(f"  ! {sym}: price stats failed ({e})", file=sys.stderr)
            continue
        imp10 = iv / np.sqrt(252) * np.sqrt(10) if iv == iv else np.nan
        rows.append({"sym": sym, "spot": spot if spot == spot else last,
                     "dte": dte, "iv_atm": iv, "rv21": rv21, "rv10": rv10,
                     "vrp": rv21 - iv if iv == iv else np.nan,
                     "imp10d": imp10, "mfe10r": mfe,
                     "ratio": mfe / imp10 if imp10 and imp10 == imp10 else np.nan,
                     "p5r": p5})

    t = pd.DataFrame(rows).set_index("sym")
    pd.set_option("display.width", 200)
    print("\n=== IMPLIED vs REALIZED  (sorted by VRP: rv21 - iv) ===")
    print(t.sort_values("vrp", ascending=False).round(2).to_string())
    print("\npositive vrp -> stock moves MORE than options charge (buy premium)")
    print("negative vrp -> options overpriced vs realized (sell premium/spreads)")
    t.to_csv(ROOT / "analysis" / "iv_edge.csv")


if __name__ == "__main__":
    main()
