"""
btc_trend.py -- "is Bitcoin trending up or down RIGHT NOW?"  (15-min bars, live)

Run:  python run.py btc

The formulas (all shown in the output so you learn to read them):

  EMA9 vs EMA21     momentum: 9-bar exp. moving avg above the 21-bar = up
  slope + R^2       linear regression on closes. slope = direction (%/hour),
                    R^2 = TREND QUALITY: 1.0 = straight line, ~0 = chop.
                    This is the crypto version of our trend_eff metric.
  RSI(14)           >60 hot, <40 weak, 45-55 = no conviction
  HH/HL structure   count of higher-highs & higher-lows in the window

Verdicts per timeframe (1h / 4h / 24h):
  TRENDING UP     score >= +2 and R^2 >= .4   (direction AND quality)
  drifting up     score >= +1
  CHOP            |score| <= 1 or R^2 < .15   (don't trade direction)
  drifting down / TRENDING DOWN mirror the above
"""
import sys

import numpy as np
import pandas as pd
import requests

import config

TD = "https://api.twelvedata.com/time_series"


def fetch_15m(outputsize=300):
    r = requests.get(TD, timeout=25, params=dict(
        symbol="BTC/USD", interval="15min", outputsize=outputsize,
        order="ASC", apikey=config.TWELVE_DATA_API_KEY))
    js = r.json()
    if "values" not in js:
        sys.exit(f"Twelve Data error: {js.get('message', js)}")
    df = pd.DataFrame(js["values"])
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c])
    df["dt"] = pd.to_datetime(df["datetime"])
    return df.reset_index(drop=True)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def slope_r2(close):
    """regression slope in %/hour + R^2 (trend quality)."""
    y = close.values
    x = np.arange(len(y))
    if len(y) < 3:
        return 0.0, 0.0
    b, a = np.polyfit(x, y, 1)
    yhat = a + b * x
    ss_res = ((y - yhat) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    pct_per_hr = b * 4 / y.mean() * 100          # 4 bars per hour
    return pct_per_hr, r2


def verdict(win):
    close = win["close"]
    e9, e21 = ema(close, 9).iloc[-1], ema(close, 21).iloc[-1]
    slp, r2 = slope_r2(close)
    # RSI needs >=15 bars; on tiny windows it's undefined and scores 0
    rs = rsi(close).iloc[-1] if len(close) >= 15 else float("nan")
    hh = (win["high"].diff() > 0).sum() / max(len(win) - 1, 1)
    hl = (win["low"].diff() > 0).sum() / max(len(win) - 1, 1)

    score = 0
    score += 1 if e9 > e21 else -1
    score += 1 if slp > 0.02 else (-1 if slp < -0.02 else 0)
    score += 1 if rs > 55 else (-1 if rs < 45 else 0)
    score += 1 if (hh + hl) / 2 > 0.55 else (-1 if (hh + hl) / 2 < 0.45 else 0)

    if abs(score) <= 1 or r2 < 0.15:
        v = "CHOP -- no tradable trend"
    elif score >= 2 and r2 >= 0.4:
        v = "TRENDING UP"
    elif score >= 2:
        v = "drifting up (weak quality)"
    elif score <= -2 and r2 >= 0.4:
        v = "TRENDING DOWN"
    else:
        v = "drifting down (weak quality)"
    return v, score, slp, r2, rs, e9, e21


def live_quote(sym):
    try:
        js = requests.get("https://api.twelvedata.com/quote", timeout=15,
                          params=dict(symbol=sym,
                                      apikey=config.TWELVE_DATA_API_KEY)).json()
        return float(js["close"]), float(js["percent_change"])
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None, None


def context():
    """Everything live that typically pushes BTC around:
    - equities risk appetite (QQQ): BTC trades like a high-beta risk asset
    - the dollar (UUP): dollar up usually = BTC headwind
    - ETH: if ETH confirms, the move is crypto-wide, not a BTC-only quirk
    - the macro calendar: CPI/FOMC/jobs move BTC too (rate expectations)
    """
    import datetime as dt
    print("\n LIVE CONTEXT (what's pushing it):")
    for sym, label, read_up, read_dn in [
        ("QQQ", "QQQ (risk appetite) ", "risk-on tailwind", "risk-off headwind"),
        ("UUP", "UUP (dollar)        ", "dollar up = BTC headwind", "dollar down = BTC tailwind"),
        ("ETH/USD", "ETH (confirmation)  ", "crypto-wide move", "crypto-wide move"),
    ]:
        px, chg = live_quote(sym)
        if px is None:
            print(f"   {label} unavailable")
            continue
        read = read_up if chg > 0 else read_dn
        print(f"   {label} {px:10,.2f}  {chg:+.2f}%   {read}")

    # nearest macro event from the calendar we already maintain
    try:
        from analyze import load_events
        ev = load_events()
        today = pd.Timestamp(dt.date.today())
        nxt = ev[(ev["Date"] >= today) & (ev["tier"] <= 2)].sort_values("Date")
        if len(nxt):
            r = nxt.iloc[0]
            print(f"   next macro event      {r['Date'].date()} "
                  f"{r.get('time_et','')} ET  {r['report']}"
                  f"   <- BTC reacts to rate-sensitive data too")
    except Exception:
        pass


def main():
    df = fetch_15m()
    last = df.iloc[-1]
    px = last["close"]
    print("=" * 66)
    print(f" BITCOIN 15-MIN TREND  |  {last['datetime']} UTC  |  ${px:,.0f}")
    print("=" * 66)

    for label, bars in [("last 1h ", 4), ("last 4h ", 16), ("last 24h", 96)]:
        win = df.tail(bars)
        v, score, slp, r2, rs, e9, e21 = verdict(win)
        chg = win["close"].iloc[-1] / win["close"].iloc[0] - 1
        print(f"\n {label}: {v}")
        rs_txt = f"{rs:.0f}" if rs == rs else "-"
        print(f"   change {chg*100:+.2f}%   slope {slp:+.3f}%/hr   "
              f"R2 {r2:.2f}   RSI {rs_txt}   EMA9{'>' if e9 > e21 else '<'}EMA21"
              f"   score {score:+d}/4")

    print("\n last 8 bars (15m):")
    for _, r in df.tail(8).iterrows():
        mv = r["close"] / r["open"] - 1
        arrow = "^" if mv > 0.0005 else ("v" if mv < -0.0005 else "-")
        print(f"   {str(r['datetime'])[5:16]}  {r['close']:9,.0f}  "
              f"{mv*100:+.2f}% {arrow}")
    context()
    print("\n How to read: trust TRENDING verdicts (direction + R2 quality).")
    print(" CHOP = the 15-min tape is noise; don't trade BTC direction off it.")
    print(" If QQQ/dollar/ETH all point the same way as the verdict, conviction")
    print(" is higher; if they disagree, the trend is more likely to stall.")


if __name__ == "__main__":
    main()
