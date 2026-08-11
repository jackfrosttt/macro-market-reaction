#!/usr/bin/env python3
"""
cheap_premium.py -- where is option premium actually CHEAP, and which side?

"Cheap" is not a low dollar price -- a $0.08 far-OTM call is the most expensive
thing on the board per unit of probability. Cheap means the option is
underpricing how much the stock actually moves. Two measures:

  vrp   = realized vol (21d, TRIMMED of its single biggest day) - ATM IV
          POSITIVE -> the stock moves more than options charge. Buyer-friendly.
          NEGATIVE -> you are overpaying vs realized. Seller-friendly.

  skew  = IV of the ~25-delta PUT - IV of the ~25-delta CALL
          POSITIVE -> puts are bid up relative to calls, so CALLS are the
          cheaper side to buy (and puts the better side to sell).
          NEGATIVE -> the reverse: unusual, means calls are being chased.

Direction context comes from the price data, not a forecast:
  ret21 / eff21 -- net 21d move and how one-way it was (Kaufman efficiency).
  eff near 0 means chop: neither calls NOR puts are a good BUY, because the
  stock pays you nothing for the premium you spend.

The combination that favours buying a CALL is: vrp > 0 (cheap vs realized),
skew > 0 (calls the cheap side), eff decent and ret21 > 0 (it actually trends up).
For a PUT: vrp > 0, skew < 0 or small, eff decent and ret21 < 0.
Nothing here forecasts direction. It tells you what you are being charged.
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

ROOT = pathlib.Path(__file__).resolve().parent

UNIVERSE = ["SPY", "QQQ", "IWM", "SMH", "XLE", "XLF", "XLV", "XLP", "GLD",
            "TLT", "USO", "NVDA", "AMD", "MU", "TSLA", "AAPL", "MSFT",
            "GOOGL", "AMZN", "META", "CRWD", "SPCX"]

EARNINGS = {  # confirmed this week; used only to flag event-inflated IV
    "MSFT": "7/29 AMC", "META": "7/29 AMC", "AAPL": "7/30 AMC",
    "AMZN": "7/30 AMC", "NVDA": "~8/26",
}


def iv_at_delta(chain, kind, target):
    """IV of the contract whose delta is closest to `target`."""
    d = chain[chain["type"] == kind].copy()
    d["delta"] = pd.to_numeric(d["delta"], errors="coerce")
    d["iv"] = pd.to_numeric(d["iv"], errors="coerce")
    d = d[(d["iv"] > 0) & d["delta"].notna()]
    if not len(d):
        return np.nan
    i = (d["delta"] - target).abs().idxmin()
    return float(d.loc[i, "iv"]) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-dte", type=int, default=14)
    ap.add_argument("--max-dte", type=int, default=45)
    ap.add_argument("symbols", nargs="*", default=UNIVERSE)
    args = ap.parse_args()

    today = dt.date.today()
    rows = []
    for sym in args.symbols:
        try:
            chain, spot = fetch_chain(sym)
            df, _ = split_partial(load(ROOT / f"daily_{sym}.csv"))
        except Exception as e:
            print(f"  ! {sym}: {e}", file=sys.stderr)
            continue
        if not spot or len(df) < 40:
            continue

        chain["dte"] = (pd.to_datetime(chain["expiry"]).dt.date
                        - today).apply(lambda x: x.days)
        near = chain[(chain["dte"] >= args.min_dte) & (chain["dte"] <= args.max_dte)]
        if not len(near):
            continue
        exp = near.sort_values("dte")["expiry"].iloc[0]
        e = near[near["expiry"] == exp]

        c = e[e["type"] == "call"].copy()
        c["iv"] = pd.to_numeric(c["iv"], errors="coerce")
        atm = c.iloc[(c["strike"] - spot).abs().argsort()[:4]]
        iv_atm = float(atm[atm["iv"] > 0]["iv"].mean() * 100)

        # realized vol, trimmed of the single largest move (earnings gaps)
        lr = np.diff(np.log(df["Close"].to_numpy(dtype=float)))[-21:]
        keep = np.abs(lr) < np.abs(lr).max()
        rv = float(lr[keep].std() * np.sqrt(252) * 100)

        r = df["Close"].pct_change().dropna().tail(21)
        ret21 = float((df["Close"].iloc[-1] / df["Close"].iloc[-22] - 1) * 100)
        eff = float(abs(r.sum()) / r.abs().sum()) if r.abs().sum() else np.nan

        iv_c25 = iv_at_delta(e, "call", 0.25)
        iv_p25 = iv_at_delta(e, "put", -0.25)
        rows.append({
            "sym": sym, "spot": round(spot, 2), "exp": exp,
            "dte": int(e["dte"].iloc[0]), "iv_atm": round(iv_atm, 1),
            "rv21t": round(rv, 1), "vrp": round(rv - iv_atm, 1),
            "iv_25c": round(iv_c25, 1), "iv_25p": round(iv_p25, 1),
            "skew": round(iv_p25 - iv_c25, 1),
            "ret21": round(ret21, 1), "eff21": round(eff, 2),
            "event": EARNINGS.get(sym, ""),
        })

    t = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print("\n=== CHEAPEST PREMIUM (vrp = trimmed realized vol - ATM IV) ===")
    print(t.sort_values("vrp", ascending=False).to_string(index=False))

    print("\n=== CALLS ARE THE CHEAP SIDE (highest put-over-call skew) ===")
    print(t.sort_values("skew", ascending=False).head(8)
          [["sym", "iv_atm", "vrp", "iv_25c", "iv_25p", "skew", "ret21",
            "eff21", "event"]].to_string(index=False))

    good = t[(t["vrp"] > 0) & (t["eff21"] >= 0.25)]
    print("\n=== PASSES BOTH FILTERS (cheap vs realized AND actually trending) ===")
    if len(good):
        print(good.sort_values("vrp", ascending=False).to_string(index=False))
        print("\n  direction: ret21>0 favours calls, ret21<0 favours puts")
    else:
        print("  NONE. Either premium is rich, or the names that are cheap are\n"
              "  chopping (eff<0.25) and will not pay for ANY long option.")
    t.to_csv(ROOT / "analysis" / "cheap_premium.csv", index=False)
    print("\n-> analysis/cheap_premium.csv")


if __name__ == "__main__":
    main()
