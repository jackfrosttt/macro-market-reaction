#!/usr/bin/env python3
"""
rotation_scan.py -- who is STILL MOVING while SPY/QQQ have gone dead.

For each ticker in the local daily_*.csv universe, over a lookback window:

  ret            total % move over the window (net direction)
  avg_rng        mean daily (High-Low)/Close  -> how much intraday travel
  ann_vol        annualized stdev of daily log returns
  eff            Kaufman efficiency ratio = |sum(r)| / sum(|r|)
                 1.0 = perfect one-way trend, ~0 = pure chop
  trend_eff      repo metric: mean of |ret_oc| / range_pct per day
  n2 / n3        # days with |close-to-close| >= 2% / 3%
  mfe10          MEDIAN best-case % move captured within 10 trading days of any
                 entry, taking the better side (this is the "can a long option
                 pay" number -- it is the realized move a directional buyer
                 could have harvested, before IV cost)
  p5             % of entries where mfe10 >= 5% (the repo backtest's bar)
  corr_spy       correlation of daily returns to SPY over the window
                 (low/negative = decoupled from the dead index)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

WINDOWS = [10, 21, 63]
HOLD = 10          # trading days a directional option position is held
PAY_BAR = 5.0      # % move that makes a long directional option pay


def load(path):
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.sort_values("Date").drop_duplicates("Date", keep="last")
    for c in ("Close", "High", "Low", "Open", "Volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Close", "High", "Low", "Open"])


def split_partial(df):
    """Twelve Data serves a LIVE partial bar while the session is open.
    Detect it (today's date, or volume far below the recent norm) and hold it
    out of the statistics -- an unfinished bar has a fake close and a
    truncated high/low, which would poison vol/return/efficiency metrics.
    Returns (complete_bars, partial_row_or_None)."""
    if len(df) < 25:
        return df, None
    last = df.iloc[-1]
    med_vol = df["Volume"].iloc[-21:-1].median()
    is_today = last["Date"].date() == pd.Timestamp.today().date()
    thin = pd.notna(med_vol) and med_vol > 0 and last["Volume"] < 0.40 * med_vol
    if is_today or thin:
        return df.iloc[:-1].copy(), last
    return df, None


def mfe_stats(close, hold=HOLD, bar=PAY_BAR):
    """Best % move available within `hold` days of each entry, better side."""
    c = np.asarray(close, dtype=float)
    n = len(c)
    if n < hold + 2:
        return np.nan, np.nan
    out = []
    for i in range(n - hold):
        fwd = c[i + 1:i + 1 + hold]
        up = (fwd.max() - c[i]) / c[i] * 100.0
        dn = (c[i] - fwd.min()) / c[i] * 100.0
        out.append(max(up, dn))
    out = np.array(out)
    return float(np.median(out)), float((out >= bar).mean() * 100.0)


def metrics(df, win, spy_ret):
    d = df.tail(win + 1).copy()
    if len(d) < win // 2:
        return None
    d["r"] = d["Close"].pct_change()
    r = d["r"].dropna()
    if len(r) < 3:
        return None

    rng = ((d["High"] - d["Low"]) / d["Close"] * 100.0).tail(win)
    ret_oc = (d["Close"] - d["Open"]).abs() / d["Open"] * 100.0
    rng_safe = ((d["High"] - d["Low"]) / d["Open"] * 100.0).replace(0, np.nan)
    teff = (ret_oc / rng_safe).tail(win)

    tot = (d["Close"].iloc[-1] / d["Close"].iloc[0] - 1.0) * 100.0
    abs_sum = r.abs().sum() * 100.0
    eff = abs(r.sum() * 100.0) / abs_sum if abs_sum > 0 else np.nan

    # correlation to SPY on aligned dates
    corr = np.nan
    if spy_ret is not None:
        j = pd.concat([d.set_index("Date")["r"], spy_ret], axis=1, join="inner").dropna()
        if len(j) >= 5:
            corr = float(j.iloc[:, 0].corr(j.iloc[:, 1]))

    return {
        "ret": tot,
        "avg_rng": float(rng.mean()),
        "ann_vol": float(r.std() * np.sqrt(252) * 100.0),
        "eff": float(eff),
        "trend_eff": float(teff.mean()),
        "n2": int((r.abs() * 100 >= 2).sum()),
        "n3": int((r.abs() * 100 >= 3).sum()),
        "corr_spy": corr,
    }


def main():
    repo = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(repo, "analysis")
    skip = {"ALL"}                      # daily_ALL.csv is a concatenated dump
    files = sorted(glob.glob(os.path.join(repo, "daily_*.csv")))

    data, live = {}, {}
    for f in files:
        sym = os.path.basename(f)[len("daily_"):-len(".csv")]
        if sym in skip:
            continue
        try:
            df = load(f)
        except Exception as e:
            print(f"  ! {sym}: {e}", file=sys.stderr)
            continue
        if len(df) < 30:
            continue
        df, partial = split_partial(df)
        if partial is not None and len(df):
            prev = df["Close"].iloc[-1]
            live[sym] = {"date": partial["Date"].date(),
                         "px": float(partial["Close"]),
                         "chg": (float(partial["Close"]) / prev - 1.0) * 100.0}
        data[sym] = df

    # reference: SPY daily returns
    spy = data.get("SPY")
    spy_ret = None
    if spy is not None:
        s = spy.set_index("Date")["Close"].pct_change().rename("spy")
        spy_ret = s

    # freshness report
    last_dates = {s: d["Date"].iloc[-1].date() for s, d in data.items()}
    newest = max(last_dates.values())
    stale = {s: d for s, d in last_dates.items() if (newest - d).days > 4}

    print(f"universe: {len(data)} tickers | newest bar: {newest}")
    if stale:
        print(f"STALE (excluded from ranking): "
              f"{', '.join(f'{s}={d}' for s, d in sorted(stale.items()))}")
    print()

    rows = []
    for sym, df in data.items():
        if sym in stale:
            continue
        rec = {"sym": sym}
        for w in WINDOWS:
            m = metrics(df, w, spy_ret)
            if m is None:
                continue
            for k, v in m.items():
                rec[f"{k}_{w}"] = v
        med, p5 = mfe_stats(df["Close"].tail(70))          # ~3mo regime
        rec["mfe10"], rec["p5"] = med, p5
        med_r, p5_r = mfe_stats(df["Close"].tail(32))       # current regime only
        rec["mfe10r"], rec["p5r"] = med_r, p5_r
        rec["last"] = float(df["Close"].iloc[-1])
        rows.append(rec)

    t = pd.DataFrame(rows).set_index("sym")
    t.to_csv(os.path.join(root, "rotation_metrics.csv"))

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    def show(title, cols, sort, n=40, asc=False):
        sub = t[cols].dropna(subset=[sort]).sort_values(sort, ascending=asc).head(n)
        print(f"\n=== {title} ===")
        print(sub.round(2).to_string())

    if live:
        print("=== LIVE (partial) BAR - held OUT of all stats below ===")
        lv = pd.DataFrame(live).T.sort_values("chg", key=lambda s: s.abs(),
                                              ascending=False)
        print(lv.head(15).round(2).to_string())
        print()

    show("STILL MOVING - last 21d (ann vol)",
         ["last", "ret_21", "ann_vol_21", "avg_rng_21", "eff_21", "trend_eff_21",
          "n2_21", "n3_21", "corr_spy_21", "mfe10r", "p5r"],
         "ann_vol_21")

    show("MOST DIRECTIONAL - last 21d (efficiency ratio)",
         ["last", "ret_21", "ann_vol_21", "eff_21", "trend_eff_21", "n2_21",
          "corr_spy_21", "mfe10", "p5"],
         "eff_21")

    show("OPTION-PAYS SCORE (median 10d capture, CURRENT regime ~30d)",
         ["last", "mfe10r", "p5r", "mfe10", "p5", "ann_vol_21", "eff_21",
          "ret_21", "corr_spy_21"],
         "mfe10r")

    show("DECOUPLED FROM SPY - last 21d (lowest correlation)",
         ["last", "corr_spy_21", "ann_vol_21", "eff_21", "ret_21", "mfe10r", "p5r"],
         "corr_spy_21", asc=True)

    print("\n=== INDEX BASELINE (the premise check) ===")
    base = [s for s in ("SPY", "QQQ", "IWM", "DIA", "RSP") if s in t.index]
    print(t.loc[base, ["last", "ret_10", "ret_21", "ret_63", "ann_vol_10",
                       "ann_vol_21", "ann_vol_63", "eff_21", "mfe10", "p5"]]
          .round(2).to_string())


if __name__ == "__main__":
    main()
