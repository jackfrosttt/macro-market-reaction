#!/usr/bin/env python3
"""
run.py -- one entry point for the whole pipeline.

    python run.py prices          refresh SPY/QQQ/IWM/DIA from Twelve Data
    python run.py prices --all    refresh the full ticker universe
    python run.py macro           rebuild the FRED macro-release calendar
    python run.py analyze         run the release-vs-reaction analysis
    python run.py all             prices -> macro -> analyze (the usual run)

Extra args after the subcommand are passed through, e.g.:
    python run.py analyze --days 120 --tier 1
    python run.py macro --start 2026-01-01 --end 2026-07-02
"""
import runpy
import sys

SUBCMDS = {"prices": "fetch_prices.py",
           "macro": "fetch_macro.py",
           "analyze": "analyze.py"}


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
        run_script(SUBCMDS[cmd], rest)
    else:
        print(f"unknown command: {cmd}\n")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
