"""
fetch_options.py -- free delayed options chain from CBOE (no key needed).

Twelve Data options need a paid plan, but CBOE publishes a delayed (~15 min)
full chain for free. We pull SPY + QQQ, store the chain in market.db, and print
a plain-English positioning summary:

  put/call VOLUME ratio   what traders are DOING today (fear vs greed)
  put/call OI ratio       how the market is POSITIONED overall
  top open-interest walls strikes with huge OI often act like magnets/pins
  ATM implied volatility  how big a move options are pricing in

Usage:
    python run.py options            # SPY + QQQ snapshot + store to db
    python run.py options --raw      # also dump the full chain to CSV
"""
import argparse
import datetime as dt
import re
import sqlite3

import pandas as pd
import requests

import config

DB = config.ROOT / "market.db"
CBOE = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")   # SPY260702C00480000


def fetch_chain(sym):
    js = requests.get(CBOE.format(sym=sym), timeout=30,
                      headers={"User-Agent": "market-data-research/1.0"}).json()
    d = js["data"]
    rows = []
    for o in d.get("options", []):
        m = OCC.match(o.get("option", ""))
        if not m:
            continue
        _, ymd, cp, strike = m.groups()
        rows.append({
            "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}",
            "type": "call" if cp == "C" else "put",
            "strike": int(strike) / 1000,
            "bid": o.get("bid"), "ask": o.get("ask"), "iv": o.get("iv"),
            "volume": o.get("volume") or 0,
            "open_interest": o.get("open_interest") or 0,
            "delta": o.get("delta"),
        })
    df = pd.DataFrame(rows)
    df["ticker"] = sym
    return df, float(d.get("current_price") or 0)


def summarize(sym, df, spot):
    print(f"\n{'='*64}\n {sym}  spot {spot:.2f}   "
          f"({len(df)} contracts, CBOE delayed)\n{'='*64}")
    cv = df[df["type"] == "call"]["volume"].sum()
    pv = df[df["type"] == "put"]["volume"].sum()
    co = df[df["type"] == "call"]["open_interest"].sum()
    po = df[df["type"] == "put"]["open_interest"].sum()
    pc_vol = pv / cv if cv else float("nan")
    pc_oi = po / co if co else float("nan")
    print(f"  put/call VOLUME ratio : {pc_vol:.2f}   "
          + ("(fear: heavy put buying)" if pc_vol > 1.1 else
             "(greed: call-heavy)" if pc_vol < 0.7 else "(neutral zone)"))
    print(f"  put/call OI ratio     : {pc_oi:.2f}")

    # nearest monthly-ish expiry 7..45 days out for walls + ATM IV
    today = dt.date.today()
    df["dte"] = (pd.to_datetime(df["expiry"]).dt.date - today).apply(lambda x: x.days)
    near = df[(df["dte"] >= 7) & (df["dte"] <= 45)]
    if len(near):
        exp = near.sort_values("dte")["expiry"].iloc[0]
        e = near[near["expiry"] == exp]
        walls = (e.groupby(["strike", "type"])["open_interest"].sum()
                 .sort_values(ascending=False).head(5))
        print(f"  biggest OI walls ({exp}):")
        for (k, t), oi in walls.items():
            tag = " <- above spot" if k > spot else " <- below spot"
            print(f"    {k:8.0f} {t:4s} OI {int(oi):>8,d}{tag}")
        atm = e.iloc[(e["strike"] - spot).abs().argsort()[:4]]
        ivs = atm[atm["iv"].astype(float) > 0]["iv"].astype(float)
        if len(ivs):
            iv = ivs.mean()
            daily = iv / (252 ** 0.5) * 100
            print(f"  ATM IV ~{iv*100:.1f}%  ->  options price a ~{daily:.2f}%/day move")
    return {"ts": dt.datetime.now().isoformat(timespec="seconds"), "ticker": sym,
            "spot": spot, "pc_volume": round(pc_vol, 3), "pc_oi": round(pc_oi, 3),
            "call_vol": int(cv), "put_vol": int(pv)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="dump full chains to CSV")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    snaps = []
    for sym in ["SPY", "QQQ"]:
        df, spot = fetch_chain(sym)
        snaps.append(summarize(sym, df, spot))
        df.to_sql(f"options_chain_{sym}", con, if_exists="replace", index=False)
        if args.raw:
            df.to_csv(config.ROOT / f"options_{sym}.csv", index=False)
    # append snapshots over time so you can see positioning SHIFT day to day
    pd.DataFrame(snaps).to_sql("options_snapshots", con, if_exists="append", index=False)
    con.commit(); con.close()
    print("\nStored chains + snapshot in market.db (table options_snapshots grows"
          "\nover time -- run this daily to track how positioning shifts).")


if __name__ == "__main__":
    main()
