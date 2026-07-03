"""
analyze.py -- does a macro-release day produce a big DIRECTIONAL move or chop?

Goal (for directional options): find which macro reports historically drive a
clean, one-way move you can ride, versus reports that only create a wide
whippy range that closes near where it opened (chop = theta/premium killer).

Key per-day metrics (computed for SPY and QQQ):
  gap        open / prev_close - 1        overnight reaction to 8:30 data
  ret_cc     close / prev_close - 1       full-day move incl. overnight
  ret_oc     close / open - 1             intraday move if you enter at the open
  range_pct  (high - low) / prev_close    how much it thrashed around
  close_loc  (close - low)/(high - low)   1=closed at highs, 0=at lows, .5=middle
  trend_eff  |ret_oc| / range_pct         DIRECTIONAL vs CHOP: share of the day's
                                          range kept as net move. High = trend.

A day is DIRECTIONAL if it made a decent net move AND kept most of its range
(high trend_eff). It's CHOP if it had a wide range but gave most of it back.

Outputs (also written to analysis/):
  1. baseline: macro-release days vs normal days
  2. per-report ranking: which reports move SPY the most, and most cleanly
  3. day-by-day log for the window with a DIRECTIONAL / CHOP / QUIET tag

Usage:
    python analyze.py                       # last 90 days, SPY + QQQ
    python analyze.py --days 120 --symbol SPY
"""
import argparse
import datetime as dt

import numpy as np
import pandas as pd

import config

# thresholds (in %/fraction) that define the day classification
BIG_MOVE = 0.0075        # |ret_cc| >= 0.75% counts as a real move
TREND_MIN = 0.55         # trend_eff >= .55 => the move stuck (directional)
CHOP_RANGE = 0.010       # range >= 1.0% ...
CHOP_TREND = 0.45        # ...but trend_eff < .45 => it thrashed and gave it back


def load_prices(sym):
    df = pd.read_csv(config.PRICE_DIR / f"daily_{sym}.csv")
    df["Date"] = pd.to_datetime(df["Date"].astype(str).str[:10])
    df = df.sort_values("Date").reset_index(drop=True)
    pc = df["Close"].shift(1)
    out = pd.DataFrame({"Date": df["Date"]})
    out["gap"] = df["Open"] / pc - 1
    out["ret_cc"] = df["Close"] / pc - 1
    out["ret_oc"] = df["Close"] / df["Open"] - 1
    rng = (df["High"] - df["Low"])
    out["range_pct"] = rng / pc
    out["close_loc"] = np.where(rng > 0, (df["Close"] - df["Low"]) / rng, 0.5)
    out["trend_eff"] = np.where(out["range_pct"] > 0,
                                out["ret_oc"].abs() / out["range_pct"], 0.0)
    return out


def classify(row):
    if abs(row["ret_cc"]) >= BIG_MOVE and row["trend_eff"] >= TREND_MIN:
        return "DIRECTIONAL"
    if row["range_pct"] >= CHOP_RANGE and row["trend_eff"] < CHOP_TREND:
        return "CHOP"
    if row["range_pct"] < 0.006:
        return "QUIET"
    return "MIXED"


def load_events():
    """FRED calendar + the user's manual supplemental_events.csv, one frame.

    Supplemental rows carry `consensus`/`actual`; when both are present we
    compute `surprise` (actual - consensus) -- the thing markets truly react to.
    """
    m = pd.read_csv(config.MACRO_CSV)
    m["source"] = "fred"
    if config.SUPPLEMENTAL_CSV.exists():
        s = pd.read_csv(config.SUPPLEMENTAL_CSV, comment="#")
        s = s.dropna(subset=["release_date", "report"])
        s["value"] = pd.to_numeric(s.get("actual"), errors="coerce")
        s["consensus"] = pd.to_numeric(s.get("consensus"), errors="coerce")
        s["surprise"] = s["value"] - s["consensus"]
        s["source"] = "manual"
        m = pd.concat([m, s], ignore_index=True)
    m["Date"] = pd.to_datetime(m["release_date"])
    return m


def load_macro(start, end):
    m = load_events()
    m = m[(m["Date"] >= start) & (m["Date"] <= end)]
    return m


def pct(x):
    return f"{x*100:+.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--symbol", default="SPY", help="primary symbol for the log")
    ap.add_argument("--tier", type=int, default=2,
                    help="include reports up to this tier (1=only top movers)")
    args = ap.parse_args()

    end = pd.Timestamp(dt.date.today())
    start = end - pd.Timedelta(days=args.days)
    config.ANALYSIS_DIR.mkdir(exist_ok=True)

    macro = load_macro(start, end)
    macro = macro[macro["tier"] <= args.tier]
    # one row per (date, report); collapse to per-date report list too
    per_date_reports = (macro.groupby("Date")["report"]
                        .apply(lambda s: ", ".join(sorted(set(s)))))

    prices = {s: load_prices(s) for s in ["SPY", "QQQ"]}
    prim = prices[args.symbol].copy()
    prim = prim[(prim["Date"] >= start) & (prim["Date"] <= end)].copy()
    prim["klass"] = prim.apply(classify, axis=1)
    prim["reports"] = prim["Date"].map(per_date_reports).fillna("")
    prim["is_event"] = prim["reports"] != ""

    lines = []
    def out(s=""):
        print(s); lines.append(s)

    out("=" * 78)
    out(f" MACRO-RELEASE vs MARKET REACTION  |  {args.symbol}  |  "
        f"{start.date()} -> {end.date()}  ({args.days}d)")
    out(f" reports included: tier <= {args.tier}   "
        f"(NOTE: values are ACTUALS from FRED; no consensus/surprise)")
    out("=" * 78)

    # ---- 1. baseline: event days vs the rest -----------------------------
    ev = prim[prim["is_event"]]
    non = prim[~prim["is_event"]]
    out("\n[1] BASELINE  (average absolute reaction)")
    out(f"{'':22s}{'n':>4s}{'|ret_cc|':>10s}{'range':>9s}"
        f"{'trend_eff':>11s}{'%directional':>14s}")
    for label, d in [("macro-release days", ev), ("normal days", non)]:
        if len(d):
            out(f"{label:22s}{len(d):4d}{d['ret_cc'].abs().mean()*100:9.2f}%"
                f"{d['range_pct'].mean()*100:8.2f}%{d['trend_eff'].mean():11.2f}"
                f"{(d['klass']=='DIRECTIONAL').mean()*100:13.0f}%")

    # ---- 2. per-report ranking ------------------------------------------
    out("\n[2] PER-REPORT REACTION  (SPY, ranked by avg |ret_cc|)")
    out(f"{'report':34s}{'n':>3s}{'|ret_cc|':>10s}{'|ret_oc|':>10s}"
        f"{'range':>8s}{'trend':>7s}{'dir%':>6s}")
    spy = prices["SPY"].set_index("Date")
    recs = []
    for report, grp in macro.groupby("report"):
        d = spy.reindex(grp["Date"].unique()).dropna(subset=["ret_cc"])
        if not len(d):
            continue
        kl = d.apply(classify, axis=1)
        recs.append({
            "report": report,
            "n": len(d),
            "abs_cc": d["ret_cc"].abs().mean(),
            "abs_oc": d["ret_oc"].abs().mean(),
            "range": d["range_pct"].mean(),
            "trend": d["trend_eff"].mean(),
            "dir_rate": (kl == "DIRECTIONAL").mean(),
        })
    rank = pd.DataFrame(recs).sort_values("abs_cc", ascending=False)
    for _, r in rank.iterrows():
        out(f"{r['report'][:33]:34s}{int(r['n']):3d}{r['abs_cc']*100:9.2f}%"
            f"{r['abs_oc']*100:9.2f}%{r['range']*100:7.2f}%"
            f"{r['trend']:7.2f}{r['dir_rate']*100:5.0f}%")
    out("\n  -> Big |ret_cc| + high trend + high dir%% = clean tradable move.")
    out("     Big range but LOW trend = chop (wide, whippy, round-trips).")

    # ---- 3. day-by-day log ----------------------------------------------
    out(f"\n[3] DAY-BY-DAY  ({args.symbol}, macro-release days in window)")
    out(f"{'date':12s}{'gap':>8s}{'ret_cc':>9s}{'ret_oc':>9s}{'range':>8s}"
        f"{'cl_loc':>7s}{'trend':>7s}  {'class':11s} reports")
    log = prim[prim["is_event"]].sort_values("Date")
    for _, r in log.iterrows():
        out(f"{r['Date'].date().isoformat():12s}{pct(r['gap']):>8s}"
            f"{pct(r['ret_cc']):>9s}{pct(r['ret_oc']):>9s}"
            f"{r['range_pct']*100:6.2f}% {r['close_loc']:6.2f}{r['trend_eff']:7.2f}"
            f"  {r['klass']:11s} {r['reports']}")

    # save artifacts
    prim.to_csv(config.ANALYSIS_DIR / "daily_metrics.csv", index=False)
    rank.to_csv(config.ANALYSIS_DIR / "report_ranking.csv", index=False)
    (config.ANALYSIS_DIR / "report.md").write_text(
        "```\n" + "\n".join(lines) + "\n```\n")
    out(f"\nSaved -> analysis/report.md, report_ranking.csv, daily_metrics.csv")


if __name__ == "__main__":
    main()
