"""
brief.py -- your macro briefing in the terminal.

The commands you'll actually use (all via run.py):

    python run.py brief          <- the 9am morning briefing (refreshes + prints)
    python run.py calendar       <- upcoming scheduled releases (next 10 days)
    python run.py history         <- last 5 months of EACH report + how SPY reacted
    python run.py cheatsheet      <- per-report: does it usually trend or chop?

Each section tells you which upcoming days are worth trading directional options
and which reports historically just chop. See README.md for the full walkthrough.
"""
import argparse
import datetime as dt

import pandas as pd
import requests

import config
from analyze import load_prices, classify, load_events

FRED = "https://api.stlouisfed.org/fred"
RID_BY_NAME = {m["name"]: rid for rid, m in config.MACRO_EVENTS.items()}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _spy_qqq():
    return load_prices("SPY").set_index("Date"), load_prices("QQQ").set_index("Date")


def report_stats(months=5):
    """Per-report avg |move| and directional-rate over the last N months (SPY)."""
    spy, _ = _spy_qqq()
    m = load_events()
    cutoff = pd.Timestamp(dt.date.today()) - pd.Timedelta(days=months * 31)
    m = m[m["Date"] >= cutoff]
    out = {}
    for report, grp in m.groupby("report"):
        d = spy.reindex(grp["Date"].unique()).dropna(subset=["ret_cc"])
        if not len(d):
            continue
        kl = d.apply(classify, axis=1)
        out[report] = {"n": len(d),
                       "abs_cc": d["ret_cc"].abs().mean(),
                       "trend": d["trend_eff"].mean(),
                       "dir_rate": (kl == "DIRECTIONAL").mean()}
    return out


def tendency_label(stats):
    """Turn dir_rate into a plain-English tag."""
    if not stats:
        return "unknown"
    r = stats["dir_rate"]
    if r >= 0.6:
        return "USUALLY TRENDS"
    if r >= 0.4:
        return "mixed"
    return "usually chops"


def upcoming(days=10):
    """Scheduled tracked releases from today .. today+days (FRED + FOMC list)."""
    today = dt.date.today()
    start, end = today.isoformat(), (today + dt.timedelta(days=days)).isoformat()
    rows = []
    for rid, meta in config.MACRO_EVENTS.items():
        if rid == 101:
            hits = [d for d in config.FOMC_DATES if start <= d <= end]
        else:
            js = requests.get(f"{FRED}/release/dates", timeout=20, params=dict(
                release_id=rid, api_key=config.FRED_API_KEY, file_type="json",
                realtime_start=start, realtime_end=end,
                include_release_dates_with_no_data="true", sort_order="asc")).json()
            hits = [r["date"] for r in js.get("release_dates", [])]
        for d in hits:
            rows.append({"date": d, "report": meta["name"], "tier": meta["tier"],
                         "at": meta["at"]})
    # + your manual entries (ISM, Fed minutes, sentiment...) from supplemental_events.csv
    if config.SUPPLEMENTAL_CSV.exists():
        s = pd.read_csv(config.SUPPLEMENTAL_CSV, comment="#")
        s = s.dropna(subset=["release_date", "report"])
        s = s[(s["release_date"] >= start) & (s["release_date"] <= end)]
        for _, r in s.iterrows():
            rows.append({"date": r["release_date"], "report": r["report"] + " *",
                         "tier": int(r["tier"]), "at": str(r["time_et"])})
    return pd.DataFrame(rows).sort_values(["date", "tier"]) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_cheatsheet(months=5):
    stats = report_stats(months)
    print(f"\nPER-REPORT CHEAT SHEET  (last {months} months, SPY)")
    print(f"{'report':34s}{'n':>3s}{'avg|move|':>10s}{'trend':>7s}{'dir%':>6s}  tendency")
    for rep, s in sorted(stats.items(), key=lambda kv: -kv[1]["dir_rate"]):
        print(f"{rep[:33]:34s}{s['n']:3d}{s['abs_cc']*100:9.2f}%{s['trend']:7.2f}"
              f"{s['dir_rate']*100:5.0f}%  {tendency_label(s)}")


def cmd_calendar(days=10):
    up = upcoming(days)
    stats = report_stats(5)
    print(f"\nUPCOMING RELEASES  (next {days} days)")
    if up.empty:
        print("  (none scheduled)"); return
    for _, r in up.iterrows():
        wd = dt.date.fromisoformat(r["date"]).strftime("%a")
        tag = tendency_label(stats.get(r["report"]))
        star = "  <-- WATCH" if tag == "USUALLY TRENDS" else ""
        print(f"  {r['date']} {wd} {r['at']:>5s}  T{r['tier']}  "
              f"{r['report'][:32]:33s} [{tag}]{star}")


def cmd_history(months=5):
    spy, qqq = _spy_qqq()
    m = load_events()
    cutoff = pd.Timestamp(dt.date.today()) - pd.Timedelta(days=months * 31)
    m = m[m["Date"] >= cutoff]
    print(f"\nLAST {months} MONTHS OF EACH REPORT  (SPY reaction)")
    for rid, meta in sorted(config.MACRO_EVENTS.items(), key=lambda kv: kv[1]["tier"]):
        rep = meta["name"]
        grp = m[m["report"] == rep].sort_values("Date")
        if grp.empty:
            continue
        print(f"\n  {rep}  (tier {meta['tier']}, {meta['at']} ET)")
        print(f"    {'date':11s}{'value':>12s}{'SPYcc':>8s}{'QQQcc':>8s}"
              f"{'trend':>7s}  class")
        for _, row in grp.iterrows():
            d = row["Date"]
            if d not in spy.index:
                continue
            s = spy.loc[d]; q = qqq.loc[d] if d in qqq.index else None
            val = f"{row['value']:.2f}" if pd.notna(row["value"]) else "n/a"
            qcc = f"{q['ret_cc']*100:+.2f}%" if q is not None else "  n/a"
            print(f"    {d.date().isoformat():11s}{val:>12s}"
                  f"{s['ret_cc']*100:+7.2f}%{qcc:>8s}{s['trend_eff']:7.2f}"
                  f"  {classify(s)}")


def cmd_brief(refresh=True):
    if refresh:
        print("Refreshing SPY/QQQ/IWM/DIA from Twelve Data ...")
        import runpy, sys
        sys.argv = ["fetch_prices.py"]
        runpy.run_path("fetch_prices.py", run_name="__main__")

    today = dt.date.today()
    print("\n" + "=" * 74)
    print(f" MACRO BRIEFING  |  {today.strftime('%A %Y-%m-%d')}")
    print("=" * 74)

    # what's today / this week
    cmd_calendar(days=8)

    # how the last handful of macro days actually reacted
    spy, qqq = _spy_qqq()
    m = load_events()
    recent = (m[m["tier"] <= 2].groupby("Date")["report"]
              .apply(lambda s: ", ".join(sorted(set(s)))).sort_index().tail(8))
    print("\nRECENT MACRO DAYS  (how SPY actually reacted)")
    print(f"  {'date':11s}{'SPYcc':>8s}{'trend':>7s}  {'class':11s} reports")
    for d, reps in recent.items():
        if d not in spy.index:
            continue
        s = spy.loc[d]
        print(f"  {d.date().isoformat():11s}{s['ret_cc']*100:+7.2f}%"
              f"{s['trend_eff']:7.2f}  {classify(s):11s} {reps}")

    cmd_cheatsheet(months=5)
    print("\nReminder: reports tagged USUALLY TRENDS are the better directional-option")
    print("days. 'usually chops' = wide but whippy; size down. See README for more.\n")


def main():
    ap = argparse.ArgumentParser(description="macro briefing")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("brief"); b.add_argument("--no-refresh", action="store_true")
    c = sub.add_parser("calendar"); c.add_argument("--days", type=int, default=10)
    h = sub.add_parser("history"); h.add_argument("--months", type=int, default=5)
    s = sub.add_parser("cheatsheet"); s.add_argument("--months", type=int, default=5)
    args = ap.parse_args()

    if args.cmd == "calendar":
        cmd_calendar(args.days)
    elif args.cmd == "history":
        cmd_history(args.months)
    elif args.cmd == "cheatsheet":
        cmd_cheatsheet(args.months)
    else:  # default / "brief"
        cmd_brief(refresh=not getattr(args, "no_refresh", False))


if __name__ == "__main__":
    main()
