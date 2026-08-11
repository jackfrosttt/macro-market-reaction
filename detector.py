"""
detector.py -- daily "informed positioning" footprint scan around the
Iran/Hormuz situation. Four independent channels, one screen:

  1. USO watch-strike put volume vs open interest (CBOE delayed).
     vol >> OI = fresh positions opened TODAY. A deal reopening the strait
     crashes oil; a surge here is the closest free proxy for a leak.
  2. USO 25-delta put/call IV skew. Skew steepening = crash insurance bid.
  3. Deal basket (daily closes): winners if deal (JETS airlines-fuel),
     losers if deal (XLE energy, FRO tankers war-premium, ITA defense,
     GLD war hedge). Divergence vs recent trend BEFORE news = footprint.
  4. Polymarket "US announces end of Iranian blockade by <date>" ladder +
     Hormuz-traffic markets. Sharp odds moves without public news are the
     purest informed-money signal free data offers.
  5. FRED 5y breakeven (T5YIE): is the bond market pricing the oil shock
     as persistent inflation or transitory?

Run:  python run.py detect        (or python detector.py)
History: appends one row/day to analysis/detector_log.csv so footprints
can be compared session-over-session.
"""
import datetime as dt

import pandas as pd
import requests

import config
import fetch_options as fo

WATCH_PUT_STRIKES = range(105, 122)     # USO deal-crash zone (spot ~128)
BASKET = ["USO", "XLE", "GLD", "FRO", "ITA", "JETS", "SPY", "TLT"]
LOG = config.ANALYSIS_DIR / "detector_log.csv"


def uso_puts():
    df, spot = fo.fetch_chain("USO")
    puts = df[(df["type"] == "put") & (df["strike"].isin(WATCH_PUT_STRIKES))].copy()
    puts = puts[puts["expiry"] <= "2026-10-01"]          # deal-window expiries
    puts["vol_oi"] = puts["volume"] / puts["open_interest"].clip(lower=1)
    hot = puts[(puts["volume"] >= 200) & (puts["vol_oi"] >= 2)]
    print(f"\n[1] USO deal-crash puts (spot {spot:.2f}; strikes 105-121, exp<=Oct 1)")
    tot_v, tot_oi = int(puts["volume"].sum()), int(puts["open_interest"].sum())
    print(f"    total watch-zone put volume {tot_v:,} vs OI {tot_oi:,}"
          f"  (ratio {tot_v / max(tot_oi, 1):.2f})")
    if hot.empty:
        print("    no fresh-opening lines (vol>=200 & vol/OI>=2) today")
    for _, r in hot.sort_values("vol_oi", ascending=False).head(6).iterrows():
        print(f"    FRESH {r['expiry']} {r['strike']:.0f}p  vol {int(r['volume']):,}"
              f" vs OI {int(r['open_interest']):,}  ({r['vol_oi']:.0f}x)")
    return df, spot, tot_v, tot_oi


def uso_skew(df, spot):
    near = df[(df["expiry"] > dt.date.today().isoformat()) &
              (df["expiry"] <= "2026-09-20") & df["iv"].notna() & (df["iv"] > 0)]
    p25 = near[(near["type"] == "put") & near["delta"].between(-0.30, -0.20)]
    c25 = near[(near["type"] == "call") & near["delta"].between(0.20, 0.30)]
    if p25.empty or c25.empty:
        print("[2] skew: insufficient IV data")
        return None
    skew = p25["iv"].mean() - c25["iv"].mean()
    print(f"\n[2] USO 25-delta skew (exp<=Sep 18): put IV {p25['iv'].mean():.1%}"
          f" - call IV {c25['iv'].mean():.1%} = {skew:+.1%}"
          f"  ({'crash-insurance bid' if skew > 0.03 else 'calls still favored' if skew < 0 else 'mild'})")
    return skew


def basket():
    print("\n[3] Deal basket (a DEAL = JETS up; USO/XLE/FRO/ITA/GLD down)")
    rows = []
    for s in BASKET:
        d = pd.read_csv(config.PRICE_DIR / f"daily_{s}.csv").tail(6)
        c = d["Close"]
        rows.append((s, (c.iloc[-1] / c.iloc[-2] - 1) * 100,
                     (c.iloc[-1] / c.iloc[0] - 1) * 100))
    for s, d1, d5 in rows:
        print(f"    {s:5s} 1d {d1:+5.1f}%   5d {d5:+5.1f}%")
    return {s: d1 for s, d1, _ in rows}


def polymarket():
    print("\n[4] Polymarket (yes-odds; watch for jumps without public news)")
    out = {}
    try:
        evs = requests.get("https://gamma-api.polymarket.com/events",
                           params={"closed": "false", "limit": 100,
                                   "order": "volume24hr", "ascending": "false"},
                           timeout=20).json()
    except (requests.RequestException, ValueError):
        print("    polymarket unreachable")
        return out
    for e in evs:
        title = (e.get("title") or "") + (e.get("slug") or "")
        if not any(k in title.lower() for k in ["hormuz", "iranian blockade", "x iran"]):
            continue
        for m in e.get("markets", []):
            q = m.get("question") or ""
            try:
                yes = float(eval(m.get("outcomePrices", "[0]"))[0])
            except Exception:
                continue
            if 0.005 < yes < 0.995:                      # skip resolved legs
                print(f"    {yes:5.1%}  {q[:64]}")
                out[q[:64]] = yes
    return out


def cot_wti():
    """CFTC managed-money net position in ICE WTI (Socrata, updates Fridays,
    positions as of Tuesday). Spec flows = the 'oil futures smart money'."""
    try:
        js = requests.get("https://publicreporting.cftc.gov/resource/72hh-3qpy.json",
                          params={"$limit": 4, "$order": "report_date_as_yyyy_mm_dd DESC",
                                  "$where": "upper(market_and_exchange_names) like "
                                            "'%CRUDE OIL%LIGHT%ICE%'"},
                          timeout=25).json()
        rows = [(r["report_date_as_yyyy_mm_dd"][:10],
                 int(float(r["m_money_positions_long_all"])) -
                 int(float(r["m_money_positions_short_all"]))) for r in js]
        if not rows:
            print("\n[6] COT: no rows"); return None
        path = "  ".join(f"{d[5:]}:{n:+,}" for d, n in reversed(rows))
        print(f"\n[6] CFTC managed-money WTI net (ICE): {path}")
        print("    (net rising toward flat/long = specs chasing oil up, deal-crash fuel builds)")
        return rows[0][1]
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"\n[6] COT unavailable: {str(e)[:50]}"); return None


def brent_wti():
    """BNO/USO close ratio: rising = Brent premium = Hormuz/global stress."""
    try:
        u = pd.read_csv(config.PRICE_DIR / "daily_USO.csv", index_col="Date")["Close"]
        b = pd.read_csv(config.PRICE_DIR / "daily_BNO.csv", index_col="Date")["Close"]
        r = (b / u).dropna()
        print(f"\n[7] Brent/WTI proxy (BNO/USO): {r.iloc[-1]:.3f}"
              f"  (5d ago {r.iloc[-6]:.3f}, 25d ago {r.iloc[-25]:.3f};"
              " rising = stress premium widening)")
        return float(r.iloc[-1])
    except (FileNotFoundError, IndexError):
        print("\n[7] Brent/WTI: refresh USO+BNO dailies first"); return None


def breakeven():
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                         params={"series_id": "T5YIE", "api_key": config.FRED_API_KEY,
                                 "file_type": "json", "sort_order": "desc", "limit": 5},
                         timeout=20).json()
        obs = [(o["date"], float(o["value"])) for o in r["observations"]
               if o["value"] != "."]
        print(f"\n[5] 5y breakeven inflation: {obs[0][1]:.2f}% ({obs[0][0]})"
              f"   5d path: {' '.join(f'{v:.2f}' for _, v in reversed(obs))}")
        return obs[0][1]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        print("\n[5] FRED breakeven unavailable")
        return None


def main():
    print("=" * 66)
    print(f" DEAL DETECTOR  |  {dt.date.today()}  |  informed-flow footprint scan")
    print("=" * 66)
    df, spot, tot_v, tot_oi = uso_puts()
    skew = uso_skew(df, spot)
    b = basket()
    pm = polymarket()
    cot_net = cot_wti()
    bw = brent_wti()
    breakeven()

    config.ANALYSIS_DIR.mkdir(exist_ok=True)
    row = {"date": dt.date.today().isoformat(), "uso_spot": spot,
           "watch_put_vol": tot_v, "watch_put_oi": tot_oi,
           "skew_25d": skew, "cot_wti_net": cot_net, "brent_wti": bw,
           **{f"ret1d_{s}": v for s, v in b.items()},
           **{f"pm_{k[:40]}": v for k, v in pm.items()}}
    log = pd.DataFrame([row])
    if LOG.exists():
        old = pd.read_csv(LOG)
        log = pd.concat([old[old["date"] != row["date"]], log], ignore_index=True)
    log.to_csv(LOG, index=False)
    print(f"\nlogged -> {LOG.name} ({len(log)} days tracked)")
    print("Read: fresh put surge + skew steepening + JETS bid + ITA/FRO offered"
          "\n      + Polymarket jump, all before news = someone knows. Any one"
          "\n      alone = noise.")


if __name__ == "__main__":
    main()
