"""
darkpool.py -- "dark money" the honest way, from two free sources.

1. FINRA ATS weekly data (api.finra.org, official): how many SPY/QQQ shares
   traded in dark pools (ATS) each week. FINRA publishes this on a ~2-4 week
   delay, so it's for spotting REGIME shifts, not day trading.

2. A volume-anomaly proxy on our own daily data (no delay): days where volume
   was way above normal but price barely moved. Classic footprint of quiet
   accumulation/distribution -- somebody big absorbing shares without moving
   the tape. It's a PROXY, not proof.

What to look for:
  - dark-pool share of volume RISING while price is flat/down -> possible
    stealth accumulation (bullish tell) ... or distribution into strength if
    price is up. Direction needs the price context printed next to it.
  - repeated high-volume/no-move days near a level -> someone is working a
    big order there.

Usage:
    python run.py darkpool               # both reports for SPY + QQQ
    python run.py darkpool --weeks 12
"""
import argparse
import datetime as dt
import sqlite3

import numpy as np
import pandas as pd
import requests

import config

DB = config.ROOT / "market.db"
FINRA = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"


def mondays_back(n):
    d = dt.date.today()
    d -= dt.timedelta(days=d.weekday())          # this week's Monday
    return [(d - dt.timedelta(weeks=i)).isoformat() for i in range(1, n + 1)]


def fetch_ats(sym, weeks):
    rows = []
    for wk in mondays_back(weeks):
        body = {"limit": 5, "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "issueSymbolIdentifier", "fieldValue": sym},
            {"compareType": "EQUAL", "fieldName": "weekStartDate", "fieldValue": wk},
            {"compareType": "EQUAL", "fieldName": "summaryTypeCode", "fieldValue": "ATS_W_SMBL"},
        ]}
        try:
            js = requests.post(FINRA, json=body, timeout=25,
                               headers={"Accept": "application/json"}).json()
        except (requests.RequestException, ValueError):
            continue
        for r in js if isinstance(js, list) else []:
            rows.append({"week": wk, "ticker": sym,
                         "ats_shares": r.get("totalWeeklyShareQuantity"),
                         "ats_trades": r.get("totalWeeklyTradeCount"),
                         "ats_notional": r.get("totalNotionalSum")})
    return pd.DataFrame(rows)


def weekly_context(sym, weeks_df):
    """Attach total volume + price change for each week from our daily data."""
    d = pd.read_csv(config.PRICE_DIR / f"daily_{sym}.csv")
    d["Date"] = pd.to_datetime(d["Date"].astype(str).str[:10])
    out = []
    for _, r in weeks_df.iterrows():
        w0 = pd.Timestamp(r["week"]); w1 = w0 + pd.Timedelta(days=4)
        wk = d[(d["Date"] >= w0) & (d["Date"] <= w1)]
        if wk.empty:
            continue
        tot_vol = wk["Volume"].sum()
        px_chg = wk["Close"].iloc[-1] / wk["Open"].iloc[0] - 1
        out.append({**r, "total_vol": int(tot_vol),
                    "dark_share": r["ats_shares"] / tot_vol if tot_vol else np.nan,
                    "week_px_chg": px_chg})
    return pd.DataFrame(out)


def report_ats(sym, weeks):
    df = weekly_context(sym, fetch_ats(sym, weeks))
    if df.empty:
        print(f"  {sym}: no ATS data returned (FINRA delay is ~2-4 weeks)")
        return df
    df = df.sort_values("week")
    avg = df["dark_share"].mean()
    print(f"\n  {sym}  (avg dark-pool share of volume: {avg*100:.1f}%)")
    print(f"    {'week':12s}{'dark shares':>13s}{'share%':>8s}{'px chg':>8s}  read")
    for _, r in df.iterrows():
        if pd.isna(r["dark_share"]):
            continue
        hot = r["dark_share"] > avg * 1.15
        read = ""
        if hot and r["week_px_chg"] <= 0:
            read = "ELEVATED dark buying into weakness? (watch)"
        elif hot:
            read = "elevated dark activity into strength"
        print(f"    {r['week']:12s}{int(r['ats_shares']):>13,d}"
              f"{r['dark_share']*100:7.1f}%{r['week_px_chg']*100:+7.1f}%  {read}")
    return df


def report_anomalies(sym, lookback=120, top=8):
    d = pd.read_csv(config.PRICE_DIR / f"daily_{sym}.csv")
    d["Date"] = pd.to_datetime(d["Date"].astype(str).str[:10])
    d = d.sort_values("Date").tail(lookback + 60).reset_index(drop=True)
    d["ret"] = d["Close"].pct_change()
    d["vol_z"] = (d["Volume"] - d["Volume"].rolling(60).mean()) / d["Volume"].rolling(60).std()
    d["absorb"] = d["vol_z"] - d["ret"].abs() * 400      # big volume, small move
    recent = d.tail(lookback).dropna(subset=["vol_z"])
    flags = recent[(recent["vol_z"] > 1.5) & (recent["ret"].abs() < 0.004)]
    print(f"\n  {sym}: high-volume / no-move days (possible quiet accumulation"
          f"/distribution), last {lookback}d:")
    if flags.empty:
        print("    none flagged")
        return
    for _, r in flags.sort_values("Date").tail(top).iterrows():
        print(f"    {r['Date'].date()}  vol {r['vol_z']:+.1f} sigma, "
              f"price {r['ret']*100:+.2f}%  close {r['Close']:.2f}")
    print("    -> repeated flags near one price level = someone working a big order")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=10)
    args = ap.parse_args()

    print("=" * 64)
    print(" DARK POOL (FINRA ATS weekly, ~2-4wk delay) ")
    print("=" * 64)
    con = sqlite3.connect(DB)
    for sym in ["SPY", "QQQ"]:
        df = report_ats(sym, args.weeks)
        if len(df):
            df.to_sql("dark_pool", con, if_exists="append", index=False)
    con.commit(); con.close()

    print("\n" + "=" * 64)
    print(" VOLUME-ANOMALY PROXY (our daily data, no delay) ")
    print("=" * 64)
    for sym in ["SPY", "QQQ", "IWM"]:
        report_anomalies(sym)
    print("\nCaveat: these are footprints, not proof. Dark-pool share is normally"
          "\n~10-20% of all volume; only the CHANGE vs its own average matters.")


if __name__ == "__main__":
    main()
