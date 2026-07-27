#!/usr/bin/env python3
"""
spy_ladder.py -- concrete SPY call ladder: what to buy, and what SPY must hit.

Live CBOE chain, one expiry, every liquid strike. For each contract:

    cost      what ONE contract costs (ask x 100)
    n@budget  how many you can buy with the budget
    BE        the SPY PRICE that makes you whole at expiry (strike + premium)
    2x / 5x   the SPY PRICE where the option is worth 2x / 5x what you paid
              (at expiry: intrinsic = m * premium  ->  S = K + m * premium)
    need%     % move in SPY required to reach breakeven
    sigma     that move measured in current-regime standard deviations
    p_BE      P(SPY finishes above breakeven), de-drifted + rescaled to today's
              realized vol  <- the conservative, regime-honest number
    p_BE_d    same but keeping the sample's historical upward drift <- optimistic
    p_touch   P(SPY EVER trades above breakeven before expiry), i.e. the odds
              you get a chance to sell for a profit rather than holding to expiry

p_BE and p_BE_d bracket the honest range. Reality sits between them, and both
ignore commissions and any slippage past paying the ask once.
"""
import argparse
import datetime as dt
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_options import fetch_chain                 # noqa: E402
from rotation_scan import load, split_partial         # noqa: E402
from otm_calls import regime_path                     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent


def probs(closes, k, prem, n, target_vol, drift):
    path = regime_path(closes, target_vol=target_vol, demean=not drift)
    if len(path) < n + 30:
        return np.nan, np.nan
    r = path[n:] / path[:-n]
    win_max = np.array([path[i:i + n + 1].max() / path[i]
                        for i in range(len(path) - n)])
    return float((r > k + prem).mean() * 100), float((win_max > k + prem).mean() * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="SPY")
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD (default: all near)")
    ap.add_argument("--budget", type=float, default=1000.0)
    ap.add_argument("--min-oi", type=int, default=500)
    args = ap.parse_args()

    chain, spot = fetch_chain(args.sym)
    df, _ = split_partial(load(ROOT / f"daily_{args.sym}.csv"))
    closes = df["Close"].to_numpy(dtype=float)[-504:]
    lr21 = np.diff(np.log(closes))[-21:]
    keep = np.abs(lr21) < np.abs(lr21).max()
    cur_vol = float(lr21[keep].std() * np.sqrt(252))

    c = chain[chain["type"] == "call"].copy()
    for col in ("ask", "bid", "open_interest", "delta"):
        c[col] = pd.to_numeric(c[col], errors="coerce")
    today = dt.date.today()
    c["dte"] = (pd.to_datetime(c["expiry"]).dt.date - today).apply(lambda x: x.days)
    if args.expiry:
        c = c[c["expiry"] == args.expiry]
    c = c[(c["strike"] > spot) & (c["ask"] > 0.02) &
          (c["open_interest"] >= args.min_oi)]
    if not len(c):
        print("no liquid OTM strikes for that expiry")
        return

    print(f"\n{args.sym} spot {spot:.2f} | current realized vol "
          f"{cur_vol*100:.1f}% (trimmed) | budget ${args.budget:,.0f}")

    rows = []
    for _, o in c.sort_values("strike").iterrows():
        n = max(1, int(round(o["dte"] * 5 / 7)))
        k, prem = o["strike"] / spot, o["ask"] / spot
        p_be, p_touch = probs(closes, k, prem, n, cur_vol, drift=False)
        p_be_d, _ = probs(closes, k, prem, n, cur_vol, drift=True)
        sig = cur_vol * np.sqrt(n / 252)
        rows.append({
            "exp": o["expiry"], "dte": int(o["dte"]), "strike": o["strike"],
            "ask": o["ask"], "cost": round(o["ask"] * 100),
            "n@budget": int(args.budget // (o["ask"] * 100)),
            "BE": round(o["strike"] + o["ask"], 2),
            "2x": round(o["strike"] + 2 * o["ask"], 2),
            "5x": round(o["strike"] + 5 * o["ask"], 2),
            "need%": round((k + prem - 1) * 100, 1),
            "sigma": round(np.log(k + prem) / sig, 2) if sig else np.nan,
            "delta": round(o["delta"], 3) if pd.notna(o["delta"]) else np.nan,
            "oi": int(o["open_interest"]),
            "p_BE": round(p_be, 1), "p_BE_d": round(p_be_d, 1),
            "p_touch": round(p_touch, 1),
        })

    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    for exp in sorted(t["exp"].unique()):
        sub = t[t["exp"] == exp]
        print(f"\n=== {args.sym} calls expiring {exp} "
              f"({sub['dte'].iloc[0]}d) ===")
        print(sub.drop(columns=["exp", "dte"]).to_string(index=False))
    t.to_csv(ROOT / "analysis" / f"{args.sym.lower()}_ladder.csv", index=False)
    print(f"\n-> analysis/{args.sym.lower()}_ladder.csv")


if __name__ == "__main__":
    main()
