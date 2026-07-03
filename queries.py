"""
queries.py -- 50 premade questions you can ask the data, no AI needed.

    python run.py q list              show every query, grouped
    python run.py q <name> [args]     run one, e.g.:

    python run.py q today             "is today something?" one-shot
    python run.py q move-z QQQ        how rare was QQQ's last move?
    python run.py q after-down2       what happens the day after -2%?
    python run.py q report CPI        full history of one report
    python run.py q em SPY 5          expected move next 5 days from IV
    python run.py q btc-spy           is BTC trading with stocks right now?

Most price queries take an optional symbol (default SPY).
"""
import datetime as dt
import sqlite3
import sys

import numpy as np
import pandas as pd

import config
from analyze import load_prices, load_events, classify

DB = config.ROOT / "market.db"


# ---------------------------------------------------------------- helpers --
def raw(sym="SPY"):
    d = pd.read_csv(config.PRICE_DIR / f"daily_{sym}.csv")
    d["Date"] = pd.to_datetime(d["Date"].astype(str).str[:10])
    return d.sort_values("Date").reset_index(drop=True)


def met(sym="SPY"):
    return load_prices(sym)


def zscore(s):
    return (s - s.mean()) / s.std()


def pctile(s, x):
    return (s < x).mean() * 100


def arg(i, default=None):
    a = sys.argv[i] if len(sys.argv) > i else default
    return a


def sym_arg(default="SPY"):
    return (arg(2, default) or default).upper()


def db():
    return sqlite3.connect(DB)


def line(r):
    n = len(r.dropna())
    if not n:
        return "n=0"
    return (f"n={n:4d}  avg {r.mean()*100:+.2f}%  median {r.median()*100:+.2f}%  "
            f"win {(r > 0).mean()*100:.0f}%")


# ============================================================ THE QUERIES ==
def q_today():
    """one-shot 'is today/yesterday something?' across SPY QQQ IWM BTC"""
    for s in ["SPY", "QQQ", "IWM", "BTC"]:
        try:
            d, m = raw(s), met(s)
        except FileNotFoundError:
            continue
        last = m.iloc[-1]
        v = d["Volume"].tail(250)
        vz = (v.iloc[-1] - v.mean()) / v.std() if v.std() else 0
        mp = pctile(m["ret_cc"].abs().tail(500), abs(last["ret_cc"]))
        rp = pctile(m["range_pct"].tail(500), last["range_pct"])
        print(f"  {s:4s} {d['Date'].iloc[-1].date()}  move {last['ret_cc']*100:+.2f}% "
              f"(p{mp:.0f})  range p{rp:.0f}  vol z{vz:+.1f}  trend {last['trend_eff']:.2f}"
              f"  -> {classify(last)}")
    print("  (p90+ move/range or |vol z|>2 = yes, it's something)")


def q_move_z():
    """how unusual was the last close-to-close move? [SYM]"""
    s = sym_arg(); m = met(s)
    x = m["ret_cc"].iloc[-1]; hist = m["ret_cc"].tail(500).dropna()
    print(f"  {s} last move {x*100:+.2f}%  z={zscore(hist).iloc[-1]:+.1f}  "
          f"percentile {pctile(hist.abs(), abs(x)):.0f} of last 500d")


def q_range_z():
    """how unusual was the last daily range? [SYM]"""
    s = sym_arg(); m = met(s)
    x = m["range_pct"].iloc[-1]; hist = m["range_pct"].tail(500).dropna()
    print(f"  {s} last range {x*100:.2f}%  percentile {pctile(hist, x):.0f} of 500d")


def q_vol_z():
    """volume z-score vs last 250 days [SYM]"""
    s = sym_arg(); d = raw(s); v = d["Volume"].tail(250)
    print(f"  {s} volume {v.iloc[-1]:,.0f}  z={(v.iloc[-1]-v.mean())/v.std():+.1f} "
          f"vs 250d avg {v.mean():,.0f}")


def q_gap_z():
    """opening gap percentile [SYM]"""
    s = sym_arg(); m = met(s)
    x = m["gap"].iloc[-1]; hist = m["gap"].tail(500).dropna()
    print(f"  {s} last gap {x*100:+.2f}%  |gap| percentile "
          f"{pctile(hist.abs(), abs(x)):.0f} of 500d")


def q_rsi():
    """14-day RSI [SYM]"""
    s = sym_arg(); c = raw(s)["Close"]
    d = c.diff(); up = d.clip(lower=0).rolling(14).mean()
    dn = (-d.clip(upper=0)).rolling(14).mean()
    r = (100 - 100 / (1 + up / dn)).iloc[-1]
    tag = "overbought >70" if r > 70 else "oversold <30" if r < 30 else "neutral"
    print(f"  {s} RSI(14) = {r:.0f}  ({tag})")


def q_atr():
    """14-day ATR in $ and % [SYM]"""
    s = sym_arg(); d = raw(s)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(),
                    (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
    a = tr.rolling(14).mean().iloc[-1]
    print(f"  {s} ATR(14) = ${a:.2f} = {a/d['Close'].iloc[-1]*100:.2f}%/day "
          f"(a 'normal' full day of movement)")


def q_realized_vol():
    """20d realized volatility, annualized -- compare with options IV [SYM]"""
    s = sym_arg(); m = met(s)
    rv = m["ret_cc"].tail(20).std() * np.sqrt(252) * 100
    print(f"  {s} 20d realized vol = {rv:.1f}% annualized")
    print(f"  -> if ATM IV (run.py options) > this, options are expensive vs recent reality")


def q_from_high():
    """distance from 52-week high / low [SYM]"""
    s = sym_arg(); d = raw(s).tail(252)
    c = d["Close"].iloc[-1]
    print(f"  {s} {c:.2f}: {c/d['High'].max()*100-100:+.1f}% from 52w high "
          f"({d['High'].max():.2f}), {c/d['Low'].min()*100-100:+.1f}% above 52w low")


def q_streak():
    """current up/down streak and how rare it is [SYM]"""
    s = sym_arg(); r = met(s)["ret_cc"].dropna()
    sign = np.sign(r.iloc[-1]); n = 0
    for x in r[::-1]:
        if np.sign(x) == sign: n += 1
        else: break
    runs = (np.sign(r) != np.sign(r).shift()).cumsum()
    maxrun = r.groupby(runs).size().max()
    print(f"  {s}: {n} {'up' if sign>0 else 'down'} days in a row "
          f"(longest in sample: {maxrun})")


def q_sma():
    """price vs 20/50/200-day moving averages [SYM]"""
    s = sym_arg(); c = raw(s)["Close"]
    px = c.iloc[-1]
    for n in [20, 50, 200]:
        ma = c.rolling(n).mean().iloc[-1]
        print(f"  {s} vs SMA{n:<3d}: {px/ma*100-100:+.1f}%  ({'above' if px>ma else 'BELOW'})")


def q_best_worst():
    """10 best and worst days, last year [SYM]"""
    s = sym_arg(); m = met(s).tail(252)
    ev = load_events(); emap = ev.groupby("Date")["report"].apply(lambda x: ",".join(sorted(set(x))[:2]))
    for label, d in [("WORST", m.nsmallest(5, "ret_cc")), ("BEST", m.nlargest(5, "ret_cc"))]:
        print(f"  {label}:")
        for _, r in d.iterrows():
            print(f"    {r['Date'].date()}  {r['ret_cc']*100:+.2f}%  {emap.get(r['Date'],'')}")


def q_drawdown():
    """current and max drawdown, 1 year [SYM]"""
    s = sym_arg(); c = raw(s).tail(252)["Close"]
    dd = c / c.cummax() - 1
    print(f"  {s} current drawdown {dd.iloc[-1]*100:.1f}%  max 1y drawdown {dd.min()*100:.1f}%")


# ------------------------------------------------ what happens after X ----
def _after(cond_col_fn, label, sym="SPY"):
    m = met(sym).dropna(subset=["ret_cc"]).reset_index(drop=True)
    idx = m.index[cond_col_fn(m)]
    nxt = m["ret_cc"].reindex(idx + 1)
    print(f"  {label}: next-day {line(nxt)}")


def q_after_down2():
    """what SPY does the day AFTER a -2% day"""
    _after(lambda m: m["ret_cc"] <= -0.02, "after <= -2% days")


def q_after_up2():
    """day after a +2% day"""
    _after(lambda m: m["ret_cc"] >= 0.02, "after >= +2% days")


def q_after_3down():
    """day after 3 consecutive down days"""
    _after(lambda m: (m["ret_cc"] < 0) & (m["ret_cc"].shift(1) < 0)
           & (m["ret_cc"].shift(2) < 0), "after 3 straight down days")


def q_after_biggap():
    """day after |gap| > 1%"""
    _after(lambda m: m["gap"].abs() > 0.01, "after |gap|>1% days")


def q_after_chop():
    """day after a CHOP day -- does the move finally come?"""
    m = met("SPY").dropna(subset=["ret_cc"]).reset_index(drop=True)
    kl = m.apply(classify, axis=1)
    nxt = m["ret_cc"].reindex(m.index[kl == "CHOP"] + 1)
    print(f"  day after CHOP: {line(nxt)}  "
          f"avg |move| {nxt.abs().mean()*100:.2f}% vs all-days {m['ret_cc'].abs().mean()*100:.2f}%")


def q_after_directional():
    """day after DIRECTIONAL -- continuation or payback?"""
    m = met("SPY").dropna(subset=["ret_cc"]).reset_index(drop=True)
    kl = m.apply(classify, axis=1)
    ix = m.index[kl == "DIRECTIONAL"]
    cont = np.sign(m["ret_cc"].reindex(ix)) * m["ret_cc"].reindex(ix + 1).values
    print(f"  day after DIRECTIONAL, same-direction return: {line(pd.Series(cont))}")


def q_dow():
    """day-of-week stats [SYM]"""
    s = sym_arg(); m = met(s).tail(500)
    g = m.groupby(m["Date"].dt.day_name())["ret_cc"]
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        if d in g.groups:
            print(f"  {d:10s} {line(g.get_group(d))}")


def q_month_season():
    """average return by calendar month [SYM]"""
    s = sym_arg(); m = met(s)
    g = (m.set_index("Date")["ret_cc"].resample("ME").sum() * 100)
    by = g.groupby(g.index.month).mean()
    for mo in range(1, 13):
        if mo in by.index:
            print(f"  {dt.date(2000,mo,1):%b}  {by[mo]:+.1f}%")


def q_turn_of_month():
    """first/last 3 trading days of month vs the middle"""
    m = met("SPY").tail(750).copy()
    m["mo"] = m["Date"].dt.to_period("M")
    pos = m.groupby("mo").cumcount()
    size = m.groupby("mo")["ret_cc"].transform("size")
    edge = (pos < 3) | (pos >= size - 3)
    print(f"  turn-of-month days : {line(m[edge]['ret_cc'])}")
    print(f"  mid-month days     : {line(m[~edge]['ret_cc'])}")


# ------------------------------------------------------------- events -----
def q_next_events():
    """next 14 days of scheduled releases"""
    import runpy
    sys.argv = ["brief.py", "calendar", "--days", "14"]
    runpy.run_path("brief.py", run_name="__main__")


def q_event_league():
    """per-report avg move + directional rate, full 2.5y"""
    spy = met("SPY").set_index("Date"); ev = load_events()
    rows = []
    for rep, g in ev.groupby("report"):
        d = spy.reindex(g["Date"].unique()).dropna(subset=["ret_cc"])
        if len(d) < 3: continue
        kl = d.apply(classify, axis=1)
        rows.append((rep, len(d), d["ret_cc"].abs().mean(), (kl == "DIRECTIONAL").mean()))
    for rep, n, mv, dr in sorted(rows, key=lambda x: -x[2]):
        print(f"  {rep[:36]:38s} n={n:3d}  avg|move| {mv*100:.2f}%  dir {dr*100:3.0f}%")


def q_best_reactions():
    """15 biggest event-day moves (any report)"""
    spy = met("SPY").set_index("Date"); ev = load_events()
    emap = ev.groupby("Date")["report"].apply(lambda x: ", ".join(sorted(set(x))[:2]))
    d = spy.reindex(emap.index).dropna(subset=["ret_cc"])
    for dtx, r in d.reindex(d["ret_cc"].abs().nlargest(15).index).iterrows():
        print(f"  {dtx.date()}  {r['ret_cc']*100:+.2f}%  trend {r['trend_eff']:.2f}  {emap[dtx]}")


def q_worst_chops():
    """event days with the widest range but no net move (option-killer days)"""
    spy = met("SPY").set_index("Date"); ev = load_events()
    emap = ev.groupby("Date")["report"].apply(lambda x: ", ".join(sorted(set(x))[:2]))
    d = spy.reindex(emap.index).dropna(subset=["ret_cc"])
    d = d[(d["range_pct"] > 0.012) & (d["trend_eff"] < 0.4)]
    for dtx, r in d.sort_values("range_pct", ascending=False).head(12).iterrows():
        print(f"  {dtx.date()}  range {r['range_pct']*100:.1f}% but closed "
              f"{r['ret_cc']*100:+.2f}%  {emap[dtx]}")


def q_report():
    """full history of one report vs SPY/QQQ: run.py q report CPI"""
    key = " ".join(sys.argv[2:]) or "CPI"
    ev = load_events()
    hits = ev[ev["report"].str.contains(key, case=False)]
    if hits.empty:
        print(f"  no report matching '{key}'. Try: " +
              ", ".join(sorted(ev["report"].unique())[:10])); return
    spy, qqq = met("SPY").set_index("Date"), met("QQQ").set_index("Date")
    for _, r in hits.sort_values("Date").iterrows():
        d = r["Date"]
        if d not in spy.index: continue
        s = spy.loc[d]; q = qqq.loc[d] if d in qqq.index else None
        print(f"  {d.date()}  SPY {s['ret_cc']*100:+.2f}% "
              f"QQQ {(q['ret_cc']*100 if q is not None else 0):+.2f}%  "
              f"trend {s['trend_eff']:.2f}  {classify(s)}")


def q_surprise():
    """consensus vs actual vs move -- for supplemental rows you've filled in"""
    ev = load_events()
    f = ev.dropna(subset=["surprise"]) if "surprise" in ev else pd.DataFrame()
    if f.empty:
        print("  no surprises computed yet -- fill consensus AND actual in "
              "supplemental_events.csv, then run.py db"); return
    spy = met("SPY").set_index("Date")
    for _, r in f.sort_values("Date").iterrows():
        s = spy.loc[r["Date"]] if r["Date"] in spy.index else None
        mv = f"SPY {s['ret_cc']*100:+.2f}%" if s is not None else "no px yet"
        print(f"  {r['Date'].date()}  {r['report'][:28]:30s} "
              f"cons {r['consensus']}  act {r['value']}  surp {r['surprise']:+.2f}  {mv}")


def q_pre_event_drift():
    """does SPY drift the day BEFORE tier-1 events?"""
    spy = met("SPY").dropna(subset=["ret_cc"]).reset_index(drop=True)
    ev = load_events(); t1 = set(ev[ev["tier"] == 1]["Date"])
    ix = spy.index[spy["Date"].isin(t1)]
    prev = spy["ret_cc"].reindex(ix - 1)
    print(f"  day BEFORE tier-1 events: {line(prev)}")


def q_post_event_drift():
    """day AFTER tier-1 events -- follow-through?"""
    spy = met("SPY").dropna(subset=["ret_cc"]).reset_index(drop=True)
    ev = load_events(); t1 = set(ev[ev["tier"] == 1]["Date"])
    ix = spy.index[spy["Date"].isin(t1)]
    ev_ret = spy["ret_cc"].reindex(ix)
    cont = np.sign(ev_ret).values * spy["ret_cc"].reindex(ix + 1).values
    print(f"  day AFTER tier-1, same-direction: {line(pd.Series(cont))}")


def q_fomc_cycle():
    """SPY around FOMC: day before / of / after"""
    spy = met("SPY").dropna(subset=["ret_cc"]).reset_index(drop=True)
    days = [pd.Timestamp(d) for d in config.FOMC_DATES]
    ix = spy.index[spy["Date"].isin(days)]
    for off, label in [(-1, "day before"), (0, "FOMC day  "), (1, "day after ")]:
        print(f"  {label}: {line(spy['ret_cc'].reindex(ix + off))}")


def q_jobs_days():
    """every jobs-report day and what SPY/QQQ did"""
    sys.argv = [sys.argv[0], "report", "Jobs"]
    q_report()


# ------------------------------------------------------------ intraday ----
def q_slots():
    """avg |move| by 30-min slot, macro vs quiet days"""
    import runpy
    sys.argv = ["patterns.py"]
    runpy.run_path("patterns.py", run_name="__main__")


def q_day():
    """30-min path of one date + events: run.py q day 2026-06-17"""
    d = arg(2, met("SPY")["Date"].iloc[-1].date().isoformat())
    con = db()
    bars = pd.read_sql(f"SELECT * FROM intraday WHERE dt LIKE '{d}%' AND ticker='SPY' ORDER BY dt", con)
    con.close()
    if bars.empty:
        print(f"  no intraday bars for {d}"); return
    ev = load_events(); reps = ev[ev["Date"] == d]["report"].tolist()
    print(f"  {d}  events: {', '.join(reps) or 'none'}")
    o = bars["open"].iloc[0]
    for _, r in bars.iterrows():
        mv = r["close"] / o - 1
        print(f"    {str(r['dt'])[11:16]}  {r['close']:8.2f}  {mv*100:+.2f}% from open "
              f"{'#'*int(abs(mv)*400)}")


def q_first30():
    """does the first 30 minutes predict the rest of the day?"""
    con = db()
    bars = pd.read_sql("SELECT * FROM intraday WHERE ticker='SPY' ORDER BY dt", con)
    con.close()
    bars["day"] = bars["dt"].str[:10]
    rows = []
    for day, g in bars.groupby("day"):
        if len(g) < 5: continue
        f30 = g["close"].iloc[0] / g["open"].iloc[0] - 1
        rest = g["close"].iloc[-1] / g["close"].iloc[0] - 1
        rows.append((f30, rest))
    df = pd.DataFrame(rows, columns=["f30", "rest"])
    big = df[df["f30"].abs() > 0.003]
    cont = np.sign(big["f30"]) * big["rest"]
    print(f"  after a >0.3% first-30min move, riding that direction to close:")
    print(f"  {line(cont)}")


# ------------------------------------------------------------- options ----
def q_pc_history():
    """put/call snapshots over time (run run.py options daily to build this)"""
    con = db()
    try:
        s = pd.read_sql("SELECT * FROM options_snapshots ORDER BY ts", con)
    except Exception:
        print("  run `python run.py options` first"); return
    finally:
        con.close()
    for _, r in s.tail(14).iterrows():
        print(f"  {r['ts'][:16]}  {r['ticker']}  spot {r['spot']:8.2f}  "
              f"P/C vol {r['pc_volume']:.2f}  P/C OI {r['pc_oi']:.2f}")


def q_iv_vs_realized():
    """is the options market over- or under-pricing movement?"""
    q_realized_vol()
    print("  now run `python run.py options` and compare the ATM IV line.")


def q_em():
    """expected move from IV: run.py q em SPY 5 [IV%] (default IV from realized)"""
    s = sym_arg(); days = float(arg(3, 5))
    m = met(s)
    iv = float(arg(4, m["ret_cc"].tail(20).std() * np.sqrt(252) * 100)) / 100
    px = raw(s)["Close"].iloc[-1]
    em = px * iv * np.sqrt(days / 252)
    print(f"  {s} @ {px:.2f}, IV {iv*100:.0f}%, {days:.0f} trading days:")
    print(f"  expected move (1 sigma) = +/- ${em:.2f}  ({em/px*100:.1f}%)  "
          f"[range {px-em:.2f} .. {px+em:.2f}]")
    print(f"  formula: spot x IV x sqrt(days/252). ~68% of the time it stays inside.")


# ------------------------------------------------------------ dark pool ---
def q_dark_trend():
    """dark-pool share trend from stored FINRA data"""
    con = db()
    try:
        d = pd.read_sql("SELECT DISTINCT * FROM dark_pool ORDER BY week", con)
    except Exception:
        print("  run `python run.py darkpool` first"); return
    finally:
        con.close()
    for _, r in d.iterrows():
        print(f"  {r['week']}  {r['ticker']}  dark {r['dark_share']*100:5.1f}%  "
              f"px {r['week_px_chg']*100:+.1f}%")


def q_absorb():
    """high-volume no-move days (quiet accumulation footprint) [SYM]"""
    import darkpool
    darkpool.report_anomalies(sym_arg())


# ------------------------------------------------------------- bitcoin ----
def q_btc():
    """live BTC 15-min trend verdict (full module)"""
    import runpy
    sys.argv = ["btc_trend.py"]
    runpy.run_path("btc_trend.py", run_name="__main__")


def q_btc_spy():
    """is BTC trading WITH stocks? 30/90d correlation of daily returns"""
    b = met("BTC").set_index("Date")["ret_cc"]
    s = met("SPY").set_index("Date")["ret_cc"]
    j = pd.concat([b, s], axis=1, keys=["btc", "spy"]).dropna()
    for n in [30, 90]:
        c = j.tail(n)["btc"].corr(j.tail(n)["spy"])
        print(f"  BTC-SPY corr last {n}d: {c:+.2f}  "
              f"({'moving together = macro-driven' if c > .4 else 'decoupled' if abs(c) < .2 else 'loose'})")


def q_btc_weekend():
    """do BTC weekend moves say anything about Monday stocks?"""
    b = met("BTC"); s = met("SPY").set_index("Date")
    b["dow"] = b["Date"].dt.dayofweek
    wkd = b[b["dow"].isin([5, 6])].groupby(b["Date"].dt.to_period("W"))["ret_cc"].sum()
    rows = []
    for wk, wret in wkd.items():
        mon = wk.start_time + pd.Timedelta(days=7)
        if mon in s.index:
            rows.append((wret, s.loc[mon, "ret_cc"]))
    df = pd.DataFrame(rows, columns=["btc_wkend", "spy_mon"]).dropna()
    up = df[df["btc_wkend"] > 0.01]["spy_mon"]; dn = df[df["btc_wkend"] < -0.01]["spy_mon"]
    print(f"  after BTC weekend > +1%: SPY Monday {line(up)}")
    print(f"  after BTC weekend < -1%: SPY Monday {line(dn)}")


def q_btc_macro():
    """how BTC reacted on tier-1 macro days (it trades rates too)"""
    b = met("BTC").set_index("Date"); ev = load_events()
    t1 = ev[ev["tier"] == 1]
    d = b.reindex(t1["Date"].unique()).dropna(subset=["ret_cc"])
    base = b["ret_cc"].tail(500).abs().mean()
    print(f"  BTC on tier-1 macro days: avg |move| {d['ret_cc'].abs().mean()*100:.2f}% "
          f"vs normal {base*100:.2f}%   {line(d['ret_cc'])}")


def q_btc_z():
    """is BTC's current move unusual?"""
    sys.argv = [sys.argv[0], "move-z", "BTC"]
    q_move_z()


# ------------------------------------------------------------- formulas ---
def q_formulas():
    """the reference card: every formula this project uses"""
    print("""
  TREND vs CHOP        trend_eff = |close-open| / (high-low)
                       > 0.6 clean trend day, < 0.4 chop
  Z-SCORE              z = (x - mean) / stdev      |z|>2 = unusual (~5%)
  EXPECTED MOVE        spot x IV x sqrt(days/252)  (1-sigma option range)
  REALIZED VOL         stdev(daily returns, 20d) x sqrt(252)
  ATR(14)              avg of true range: max(H-L, |H-prevC|, |L-prevC|)
  RSI(14)              100 - 100/(1+avgGain/avgLoss)   >70 hot, <30 washed
  GAP                  open/prevClose - 1     (overnight reaction)
  CLOSE LOCATION       (close-low)/(high-low)  1=closed at highs
  REGRESSION R^2       trend QUALITY: 1 = straight line, 0 = noise
  OPTION BREAKEVEN     call: strike + premium   put: strike - premium
  POSITION SIZE        risk$ / (entry - stop)  = shares/contract count
  KELLY (fraction)     win% - loss%/(avgWin/avgLoss)  -- bet less than this
  """)


def q_breakeven():
    """option breakeven: run.py q breakeven 750 3.50 call"""
    strike = float(arg(2, 0)); prem = float(arg(3, 0)); typ = arg(4, "call")
    if not strike:
        print("  usage: run.py q breakeven STRIKE PREMIUM call|put"); return
    be = strike + prem if typ == "call" else strike - prem
    print(f"  {typ} {strike:.0f} @ {prem:.2f}: breakeven {be:.2f} "
          f"(needs {'+' if typ=='call' else '-'}{prem/strike*100:.2f}% past strike by expiry)")


def q_corr():
    """correlation of any two symbols, 90d: run.py q corr QQQ TLT"""
    a, b = (arg(2, "QQQ") or "QQQ").upper(), (arg(3, "TLT") or "TLT").upper()
    j = pd.concat([met(a).set_index("Date")["ret_cc"],
                   met(b).set_index("Date")["ret_cc"]], axis=1, keys=[a, b]).dropna()
    print(f"  {a}-{b} corr: 30d {j.tail(30)[a].corr(j.tail(30)[b]):+.2f}   "
          f"90d {j.tail(90)[a].corr(j.tail(90)[b]):+.2f}")


def q_beta():
    """beta of a symbol vs SPY, 90d: run.py q beta NVDA"""
    s = sym_arg("QQQ")
    j = pd.concat([met(s).set_index("Date")["ret_cc"],
                   met("SPY").set_index("Date")["ret_cc"]], axis=1, keys=[s, "SPY"]).dropna().tail(90)
    beta = j[s].cov(j["SPY"]) / j["SPY"].var()
    print(f"  {s} beta vs SPY (90d): {beta:.2f}  "
          f"(a 1% SPY day 'should' move {s} ~{beta:.1f}%)")


# ============================================================== registry ==
REGISTRY = {
    "IS THIS SOMETHING? (price checks)": {
        "today": q_today, "move-z": q_move_z, "range-z": q_range_z,
        "vol-z": q_vol_z, "gap-z": q_gap_z, "rsi": q_rsi, "atr": q_atr,
        "realized-vol": q_realized_vol, "from-high": q_from_high,
        "streak": q_streak, "sma": q_sma, "best-worst": q_best_worst,
        "drawdown": q_drawdown,
    },
    "WHAT HAPPENS AFTER X": {
        "after-down2": q_after_down2, "after-up2": q_after_up2,
        "after-3down": q_after_3down, "after-biggap": q_after_biggap,
        "after-chop": q_after_chop, "after-directional": q_after_directional,
        "dow": q_dow, "month-season": q_month_season,
        "turn-of-month": q_turn_of_month,
    },
    "MACRO EVENTS": {
        "next-events": q_next_events, "event-league": q_event_league,
        "best-reactions": q_best_reactions, "worst-chops": q_worst_chops,
        "report": q_report, "surprise": q_surprise,
        "pre-event-drift": q_pre_event_drift, "post-event-drift": q_post_event_drift,
        "fomc-cycle": q_fomc_cycle, "jobs-days": q_jobs_days,
    },
    "INTRADAY TIMING": {
        "slots": q_slots, "day": q_day, "first30": q_first30,
    },
    "OPTIONS": {
        "pc-history": q_pc_history, "iv-vs-realized": q_iv_vs_realized,
        "em": q_em, "breakeven": q_breakeven,
    },
    "DARK POOL": {
        "dark-trend": q_dark_trend, "absorb": q_absorb,
    },
    "BITCOIN & CROSS-ASSET": {
        "btc": q_btc, "btc-spy": q_btc_spy, "btc-weekend": q_btc_weekend,
        "btc-macro": q_btc_macro, "btc-z": q_btc_z, "corr": q_corr, "beta": q_beta,
    },
    "REFERENCE": {
        "formulas": q_formulas,
    },
}
FLAT = {name: fn for grp in REGISTRY.values() for name, fn in grp.items()}


def main():
    name = arg(1, "list")
    if name in ("list", "-h", "--help"):
        print(__doc__)
        for grp, items in REGISTRY.items():
            print(f"\n {grp}")
            for n, fn in items.items():
                print(f"   {n:20s} {(fn.__doc__ or '').strip().splitlines()[0]}")
        return
    fn = FLAT.get(name)
    if fn is None:
        close = [n for n in FLAT if name in n]
        print(f"unknown query '{name}'." + (f" did you mean: {close}?" if close else
              " run `python run.py q list`"))
        return
    print(f"[{name}] {(fn.__doc__ or '').strip().splitlines()[0]}")
    fn()


if __name__ == "__main__":
    main()
