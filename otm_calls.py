#!/usr/bin/env python3
"""
otm_calls.py -- can $1000 of LONG OTM CALLS actually make money right now?

Not theory: pulls the live CBOE chain, keeps only contracts you can actually
afford, and backtests THAT EXACT CONTRACT against the underlying's real history.

For a call with strike K and ask A on spot S, define in relative terms
    k = K/S      (strike as a multiple of spot)
    c = A/S      (premium as a fraction of spot)
Then for every historical N-trading-day window (N = DTE in trading days):
    r      = S_end / S_start
    payoff = max(0, r - k)
    profit = payoff - c
  exp_ret  = mean(profit) / c   -> historical return on premium, HELD TO EXPIRY
  p_itm    = P(r > k)           -> odds it expires in the money at all
  p_be     = P(r > k + c)       -> odds it expires past breakeven
  p_touch  = P(max(r) > k + c)  -> odds it EVER traded past breakeven, i.e. the
                                   optimistic bound where you sell early

exp_ret is the conservative (hold-to-expiry) number, p_touch the optimistic one.
The truth for a real trader who takes profits is between them.

CAVEATS (read these):
  * Uses the underlying's realized history, so it bakes in that period's DRIFT.
    A stock that trended up for 2 years makes its calls look great in-sample.
    That is exactly the "it worked before" trap -- check exp_ret across BOTH
    lookbacks and distrust anything that only works in the long one.
  * Ignores IV changes, early assignment, and any bid/ask slippage beyond
    paying the ask once. Real fills on wide spreads are worse.
  * Ignores commissions.
"""
import argparse
import datetime as dt
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_options import fetch_chain                      # noqa: E402
from rotation_scan import load, split_partial              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
LOOKBACKS = {"2y": 504, "1y": 252}


def hist_closes(sym):
    df, _ = split_partial(load(ROOT / f"daily_{sym}.csv"))
    return df["Close"].to_numpy(dtype=float)


def regime_path(closes, target_vol=None, demean=False):
    """Rebuild a synthetic price path from the same daily returns, optionally
    de-drifted and rescaled to today's realized vol.

    Why: a raw backtest of a long call inherits the sample's DRIFT and VOL.
    SPY realized 16.9% vol and +14.4%/yr drift over the last 2y but is realizing
    11.1% now -- so raw history both pushes the stock up for free and makes big
    moves look more common than the current regime supports. Both effects
    inflate OTM call expectancy. De-meaning removes the free drift; rescaling
    matches the move distribution to now. Path shape / vol clustering survive."""
    lr = np.diff(np.log(closes))
    if demean:
        lr = lr - lr.mean()
    if target_vol:
        cur = lr.std() * np.sqrt(252)
        if cur > 0:
            lr = lr * (target_vol / cur)
    return np.concatenate([[1.0], np.exp(np.cumsum(lr))])


def contract_stats(closes, k, c, n):
    """k = strike/spot, c = premium/spot, n = holding period in trading days."""
    if len(closes) < n + 30:
        return None
    start = closes[:-n]
    end = closes[n:]
    r = end / start
    # running max over each forward window, for the touch probability
    win_max = np.array([closes[i:i + n + 1].max() / closes[i]
                        for i in range(len(closes) - n)])
    payoff = np.maximum(0.0, r - k)
    profit = payoff - c
    return {
        "p_itm": float((r > k).mean() * 100),
        "p_be": float((r > k + c).mean() * 100),
        "p_touch": float((win_max > k + c).mean() * 100),
        "exp_ret": float(profit.mean() / c * 100),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=1000.0)
    ap.add_argument("--min-dte", type=int, default=7)
    ap.add_argument("--max-dte", type=int, default=60)
    ap.add_argument("--min-oi", type=int, default=250,
                    help="skip illiquid strikes you can't get out of")
    ap.add_argument("symbols", nargs="*", default=None)
    args = ap.parse_args()

    syms = args.symbols or ["NVDA", "AMD", "MU", "SMH", "TSLA", "AAPL", "MSFT",
                            "GOOGL", "META", "AMZN", "CRWD", "QQQ", "SPY",
                            "XLE", "USO", "IWM"]
    today = dt.date.today()
    rows = []
    for sym in syms:
        try:
            chain, spot = fetch_chain(sym)
            closes = hist_closes(sym)
        except Exception as e:
            print(f"  ! {sym}: {e}", file=sys.stderr)
            continue
        if not spot or len(closes) < 300:
            continue
        # today's realized vol, TRIMMED: drop the single largest move so one
        # earnings gap can't set the whole forward vol assumption (TSLA's rv21
        # is 75% with its 7/23 gap, 58% without it).
        lr21 = np.diff(np.log(closes))[-21:]
        keep = np.abs(lr21) < np.abs(lr21).max()
        cur_vol = float(lr21[keep].std() * np.sqrt(252))

        c = chain[chain["type"] == "call"].copy()
        c["ask"] = pd.to_numeric(c["ask"], errors="coerce")
        c["bid"] = pd.to_numeric(c["bid"], errors="coerce")
        c["open_interest"] = pd.to_numeric(c["open_interest"], errors="coerce")
        c["dte"] = (pd.to_datetime(c["expiry"]).dt.date - today).apply(lambda x: x.days)
        c = c[(c["dte"] >= args.min_dte) & (c["dte"] <= args.max_dte)]
        c = c[(c["strike"] > spot)]                       # OTM only
        c = c[(c["ask"] > 0.05) & (c["ask"] * 100 <= args.budget)]
        c = c[c["open_interest"] >= args.min_oi]
        if not len(c):
            continue

        for _, o in c.iterrows():
            n = max(1, int(round(o["dte"] * 5 / 7)))       # calendar -> trading days
            k, prem = o["strike"] / spot, o["ask"] / spot
            rec = {"sym": sym, "spot": round(spot, 2), "exp": o["expiry"],
                   "dte": int(o["dte"]), "strike": o["strike"],
                   "ask": o["ask"], "cost": round(o["ask"] * 100, 0),
                   "otm%": round((k - 1) * 100, 1),
                   "be%": round((k + prem - 1) * 100, 1),
                   "oi": int(o["open_interest"]),
                   "spread%": round((o["ask"] - o["bid"]) / o["ask"] * 100, 0)
                              if o["ask"] else np.nan}
            ok = True
            for label, lb in LOOKBACKS.items():
                s = contract_stats(closes[-lb:], k, prem, n)
                if s is None:
                    ok = False
                    break
                rec[f"p_be_{label}"] = round(s["p_be"], 1)
                rec[f"p_touch_{label}"] = round(s["p_touch"], 1)
                rec[f"exp_{label}"] = round(s["exp_ret"], 0)
            # regime-matched: de-drifted and rescaled to CURRENT realized vol
            sm = contract_stats(regime_path(closes[-504:], target_vol=cur_vol,
                                            demean=True), k, prem, n)
            if sm is not None:
                rec["p_be_adj"] = round(sm["p_be"], 1)
                rec["p_touch_adj"] = round(sm["p_touch"], 1)
                rec["exp_adj"] = round(sm["exp_ret"], 0)
                # Reliability. Overlapping windows are not independent: a 504-day
                # sample holds only ~(504-n)/n independent n-day windows. The
                # expectancy of a deep-OTM call is driven ENTIRELY by the rare
                # payoff events, so if the expected number of independent
                # winners is tiny the estimate is noise, not edge.
                n_eff = max(1.0, (504 - n) / n)
                rec["n_eff"] = round(n_eff, 1)
                rec["hits_eff"] = round(sm["p_be"] / 100 * n_eff, 2)
                rec["reliable"] = rec["hits_eff"] >= 5
                # how many sigma the breakeven move is, in the current regime
                sig = cur_vol * np.sqrt(n / 252)
                rec["be_sigma"] = round(np.log(k + prem) / sig, 2) if sig else np.nan
            else:
                ok = False
            if ok:
                rows.append(rec)

    if not rows:
        print("no affordable, liquid OTM calls found")
        return
    t = pd.DataFrame(rows)
    t["worst_exp"] = t[["exp_2y", "exp_1y"]].min(axis=1)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)

    cols = ["sym", "spot", "exp", "dte", "strike", "ask", "cost", "otm%", "be%",
            "be_sigma", "oi", "spread%", "exp_2y", "exp_1y",
            "p_be_adj", "exp_adj", "hits_eff", "reliable"]
    print("\n=== RAW-HISTORY RANKING (drift+vol contaminated -- the trap) ===")
    print(t.sort_values("worst_exp", ascending=False).head(10)[cols].to_string(index=False))

    rel = t[t["reliable"]]
    print(f"\n=== REGIME-MATCHED + STATISTICALLY RELIABLE "
          f"({len(rel)} of {len(t)} contracts) ===")
    if len(rel):
        print(rel.sort_values("exp_adj", ascending=False).head(20)[cols]
              .to_string(index=False))
    else:
        print("  NONE. Every affordable OTM call's expectancy rests on too few\n"
              "  independent tail events to be distinguishable from noise.")

    print(f"\n=== SCOREBOARD (of {len(t)} affordable contracts) ===")
    print(f"  positive expectancy, RAW history both lookbacks : "
          f"{int((t['worst_exp'] > 0).sum())}")
    print(f"  positive expectancy, REGIME-MATCHED             : "
          f"{int((t['exp_adj'] > 0).sum())}")
    print(f"  ... AND statistically reliable                  : "
          f"{int(((t['exp_adj'] > 0) & t['reliable']).sum())}")
    print(f"  >=50% odds of expiring past breakeven           : "
          f"{int((t['p_be_adj'] >= 50).sum())}")
    print(f"  median breakeven move required                  : "
          f"+{t['be%'].median():.1f}%  ({t['be_sigma'].median():.2f} sigma)")
    t.to_csv(ROOT / "analysis" / "otm_calls.csv", index=False)
    print(f"\nfull table -> analysis/otm_calls.csv")


if __name__ == "__main__":
    main()
