#!/usr/bin/env python3
"""
run.py -- one entry point for the whole pipeline.

    python run.py brief           <- 9am morning briefing (refresh + what to watch)
    python run.py calendar        upcoming scheduled releases (next 10 days)
    python run.py history         last 5 months of each report + SPY reaction
    python run.py cheatsheet      per-report: does it usually trend or chop?

    python run.py prices          refresh SPY/QQQ/IWM/DIA from Twelve Data
    python run.py prices --all    refresh the full ticker universe
    python run.py macro           rebuild the FRED macro-release calendar
    python run.py analyze         run the release-vs-reaction analysis
    python run.py all             prices -> macro -> analyze (the usual run)

Extra args after the subcommand are passed through, e.g.:
    python run.py brief --no-refresh
    python run.py calendar --days 14
    python run.py history --months 5
    python run.py analyze --days 120 --tier 1
    python run.py macro --start 2026-02-01 --end 2026-07-02
"""
import runpy
import sys

SUBCMDS = {"prices": "fetch_prices.py",
           "macro": "fetch_macro.py",
           "analyze": "analyze.py",
           "brief": "brief.py",
           "calendar": "brief.py",
           "history": "brief.py",
           "cheatsheet": "brief.py",
           "patterns": "patterns.py",
           "db": "build_db.py",
           "intraday": "fetch_intraday.py",
           "options": "fetch_options.py",
           "darkpool": "darkpool.py",
           "backtest": "backtest.py",
           "sync": "sync_public.py",
           "q": "queries.py",
           "btc": "btc_trend.py"}


def run_script(script, argv):
    sys.argv = [script] + argv
    runpy.run_path(script, run_name="__main__")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "all":
        run_script("fetch_prices.py", [])
        run_script("fetch_macro.py", [])
        run_script("analyze.py", rest)
    elif cmd in SUBCMDS:
        script = SUBCMDS[cmd]
        # brief.py uses subparsers, so it needs the command name as argv[1]
        argv = [cmd] + rest if script == "brief.py" else rest
        run_script(script, argv)
    else:
        print(f"unknown command: {cmd}\n")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
