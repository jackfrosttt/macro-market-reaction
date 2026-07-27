#!/usr/bin/env python3
"""
bounce_study.py -- does buying a violent down day actually pay?

Today (7/27/26) is a forced-liquidation flush in semis. The instinctive trade is
OTM calls on the bounce. This measures whether that instinct has ever had an
edge, per ticker, using real daily history.

Condition: a single-day close-to-close drop of at least THRESH%.
Then, over the next 1/3/5/10 trading days, report:
    n        how many times this setup occurred (small n = don't trust it)
    p_up     % of the time the stock was higher
    med      median forward return
    mean     mean forward return
    p5 / p10 % of the time it gained >=5% / >=10%  <- what an OTM call needs

An OTM call needs a BIG fast move, so p5/p10 matter far more than p_up.
Baseline rows show the unconditional distribution over the same history, so you
can see whether the flush actually changes anything or just feels like it does.
"""
import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from rotation_scan import load, split_partial              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
HORIZONS = [1, 3, 5, 10]


def study(sym, thresh, lookback):
    df, _ = split_partial(load(ROOT / f"daily_{sym}.csv"))
    c = df["Close"].to_numpy(dtype=float)
    if lookback:
        c = c[-lookback:]
    r = np.diff(c) / c[:-1] * 100.0            # r[i] is the return INTO day i+1
    out = []
    trig = np.where(r <= -thresh)[0] + 1       # index of the flush day itself
    for h in HORIZONS:
        # conditional
        idx = trig[trig + h < len(c)]
        if len(idx):
            fwd = (c[idx + h] / c[idx] - 1) * 100
            out.append({"sym": sym, "cond": f"after <={-thresh:.0f}%", "h": h,
                        "n": len(fwd), "p_up": (fwd > 0).mean() * 100,
                        "med": np.median(fwd), "mean": fwd.mean(),
                        "p5": (fwd >= 5).mean() * 100,
                        "p10": (fwd >= 10).mean() * 100})
        # baseline
        base_i = np.arange(0, len(c) - h)
        fwdb = (c[base_i + h] / c[base_i] - 1) * 100
        out.append({"sym": sym, "cond": "baseline", "h": h, "n": len(fwdb),
                    "p_up": (fwdb > 0).mean() * 100, "med": np.median(fwdb),
                    "mean": fwdb.mean(), "p5": (fwdb >= 5).mean() * 100,
                    "p10": (fwdb >= 10).mean() * 100})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresh", type=float, default=5.0)
    ap.add_argument("--lookback", type=int, default=1260, help="trading days (0=all)")
    ap.add_argument("symbols", nargs="*",
                    default=["AMD", "NVDA", "MU", "SMH", "SOXL", "TSLA", "CRWD"])
    args = ap.parse_args()

    rows = []
    for s in args.symbols:
        try:
            rows += study(s, args.thresh, args.lookback)
        except Exception as e:
            print(f"  ! {s}: {e}", file=sys.stderr)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(f"\n=== FORWARD RETURNS AFTER A <=-{args.thresh:.0f}% DAY "
          f"(last {args.lookback or 'all'} sessions) ===")
    for s in args.symbols:
        sub = t[t["sym"] == s]
        if not len(sub):
            continue
        print(f"\n{s}:")
        print(sub.drop(columns=["sym"]).round(1).to_string(index=False))
    t.to_csv(ROOT / "analysis" / "bounce_study.csv", index=False)
    print("\n-> analysis/bounce_study.csv")
    print("compare each 'after' row to the 'baseline' row at the same horizon:\n"
          "if p5/p10 aren't clearly higher, the flush gives you no edge.")


if __name__ == "__main__":
    main()
