"""
patterns.py -- mine the 30-min data for WHEN moves happen and hidden patterns.

Not looking for anything the data "says" -- looking for structure it doesn't
advertise: which 30-min slots move most, when the day's high/low gets set, and
whether the morning direction trends into the close or fades (reverses).

Run:  python run.py patterns          (needs: run.py intraday first)
"""
import sqlite3
import numpy as np
import pandas as pd
import config

DB = config.ROOT / "market.db"
SLOTS = ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00",
         "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]


def load(ticker="SPY"):
    con = sqlite3.connect(DB)
    df = pd.read_sql(f"SELECT * FROM intraday WHERE ticker='{ticker}'", con)
    ev = pd.read_sql("SELECT DISTINCT date FROM event_reactions", con)
    con.close()
    df["dt"] = pd.to_datetime(df["dt"])
    df["day"] = df["dt"].dt.date.astype(str)
    df["time"] = df["dt"].dt.strftime("%H:%M")
    df["bar_move"] = df["close"] / df["open"] - 1          # move within the bar
    df["bar_range"] = (df["high"] - df["low"]) / df["open"]  # thrash within bar
    macro_days = set(ev["date"])
    df["is_macro"] = df["day"].isin(macro_days)
    return df, macro_days


def by_slot(df, mask=None):
    d = df if mask is None else df[mask]
    g = d.groupby("time").agg(abs_move=("bar_move", lambda x: x.abs().mean()),
                              rng=("bar_range", "mean"))
    return g.reindex(SLOTS)


def price_at(day_df, t):
    h = day_df[day_df["time"] == t]
    return float(h["close"].iloc[0]) if len(h) else np.nan


def main():
    df, macro_days = load("SPY")
    days = sorted(df["day"].unique())
    print(f"SPY 30-min data: {len(days)} sessions "
          f"({days[0]} .. {days[-1]}), {len(macro_days)} macro days\n")

    # ---- 1. which 30-min slot moves the most? ---------------------------
    print("[1] AVERAGE MOVE BY TIME OF DAY  (|bar move| and bar range, %)")
    alls = by_slot(df); mac = by_slot(df, df["is_macro"]); non = by_slot(df, ~df["is_macro"])
    print(f"  {'slot':7s}{'all|move|':>11s}{'all range':>11s}"
          f"{'macro|mv|':>11s}{'quiet|mv|':>11s}")
    for t in SLOTS:
        print(f"  {t:7s}{alls.loc[t,'abs_move']*100:10.3f}%{alls.loc[t,'rng']*100:10.3f}%"
              f"{mac.loc[t,'abs_move']*100:10.3f}%{non.loc[t,'abs_move']*100:10.3f}%")
    top = alls["abs_move"].idxmax()
    print(f"  -> most active slot overall: {top}  "
          f"| power hour 15:00-16:00 vs midday 12:00: "
          f"{alls.loc['15:00','abs_move']/alls.loc['12:00','abs_move']:.1f}x")

    # ---- 2. when is the day's HIGH and LOW set? -------------------------
    hi_t, lo_t = [], []
    for day, g in df.groupby("day"):
        g = g.sort_values("dt")
        hi_t.append(g.loc[g["high"].idxmax(), "time"])
        lo_t.append(g.loc[g["low"].idxmin(), "time"])
    print("\n[2] WHEN THE DAY'S EXTREME IS SET  (% of days)")
    ht = pd.Series(hi_t).value_counts(normalize=True).reindex(SLOTS).fillna(0)
    lt = pd.Series(lo_t).value_counts(normalize=True).reindex(SLOTS).fillna(0)
    print(f"  {'slot':7s}{'day HIGH':>10s}{'day LOW':>10s}")
    for t in SLOTS:
        bar = "#" * int((ht[t] + lt[t]) * 60)
        print(f"  {t:7s}{ht[t]*100:9.0f}%{lt[t]*100:9.0f}%  {bar}")
    early = ht.loc[:'10:00'].sum() + lt.loc[:'10:00'].sum()
    late = ht.loc['15:00':].sum() + lt.loc['15:00':].sum()
    print(f"  -> extremes set in first 30m: {early/2*100:.0f}%   "
          f"in last hour: {late/2*100:.0f}%")

    # ---- 3. does the morning trend into the close, or fade? -------------
    rows = []
    for day, g in df.groupby("day"):
        g = g.sort_values("dt")
        o = float(g["open"].iloc[0]); c = float(g["close"].iloc[-1])
        p10 = price_at(g, "10:00"); p1130 = price_at(g, "11:30"); p1330 = price_at(g, "13:30")
        rows.append({"day": day, "macro": day in macro_days,
                     "first30": p10/o-1, "morning": p1130/o-1,
                     "rest": c/p1130-1 if p1130 else np.nan,
                     "am": p1330/o-1 if p1330 else np.nan,
                     "pm": c/p1330-1 if p1330 else np.nan,
                     "day": day})
    r = pd.DataFrame(rows)
    def corr(a, b, m=None):
        d = r if m is None else r[r["macro"] == m]
        return d[a].corr(d[b])
    print("\n[3] TREND vs FADE  (correlation of early move -> later move)")
    print(f"  first30m (9:30-10:00) -> rest of day : {corr('first30','rest'):+.2f}"
          f"   (+ = trends, - = fades)")
    print(f"  morning (open-11:30)  -> afternoon    : {corr('morning','rest'):+.2f}")
    print(f"  AM (open-1:30pm)      -> PM (1:30-close): {corr('am','pm'):+.2f}")
    print(f"     on MACRO days      AM -> PM          : {corr('am','pm',True):+.2f}")
    print(f"     on QUIET days      AM -> PM          : {corr('am','pm',False):+.2f}")
    # how often the afternoon reverses the morning
    both = r.dropna(subset=["am", "pm"])
    rev = ((np.sign(both["am"]) != np.sign(both["pm"])) & (both["am"].abs() > 0.002)).mean()
    print(f"  -> afternoon reverses a real morning move on {rev*100:.0f}% of days")


if __name__ == "__main__":
    main()
