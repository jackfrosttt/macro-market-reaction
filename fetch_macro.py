"""
fetch_macro.py -- build the macro-release calendar from FRED.

For each report in config.MACRO_EVENTS we ask FRED two things:
  1. the official RELEASE DATES (when the number hit the wire), and
  2. the ACTUAL headline value for that report (latest observations).

We then line up each release date with the value that was published on it, and
write one tidy row per (report, release date) to macro_releases.csv.

Usage:
    python fetch_macro.py                # last ~6 months (default)
    python fetch_macro.py --start 2026-01-01 --end 2026-07-02
"""
import argparse
import datetime as dt
import sys
import time

import pandas as pd
import requests

import config

FRED = "https://api.stlouisfed.org/fred"


def _get(path, **params):
    params.update(api_key=config.FRED_API_KEY, file_type="json")
    for attempt in range(4):
        try:
            r = requests.get(f"{FRED}/{path}", params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            # FRED rate limit is generous; back off just in case
            time.sleep(1 + attempt)
        except requests.RequestException:
            time.sleep(1 + attempt)
    raise RuntimeError(f"FRED request failed: {path} {params}")


def release_dates(release_id, start, end):
    """Dates (YYYY-MM-DD) this release was published within [start, end]."""
    js = _get("release/dates",
              release_id=release_id,
              realtime_start=start, realtime_end=end,
              include_release_dates_with_no_data="false",
              sort_order="asc", limit=1000)
    return [r["date"] for r in js.get("release_dates", [])]


def series_vintage(series_id, start, end):
    """
    Observations with vintage dates so we can find the value AS RELEASED.
    Returns list of dicts: date (period), realtime_start (when published), value.
    """
    js = _get(f"series/observations",
              series_id=series_id,
              realtime_start=start, realtime_end=end,
              sort_order="asc", limit=100000, output_type=2)  # 2 = all vintages
    return js.get("observations", [])


def series_plain(series_id, end):
    """Fallback: latest-vintage observations (output_type=1). Values may include
    later revisions, but this always works even for huge daily series."""
    js = _get("series/observations", series_id=series_id,
              observation_start="2023-06-01", observation_end=end,
              sort_order="asc", limit=100000)
    return [o for o in js.get("observations", [])
            if o.get("value") not in (".", None, "")]


def value_plain(obs, release_date):
    """Most recent period completed BEFORE the release date = the fresh print
    (approximately -- ignores revisions)."""
    pool = [o for o in obs if o["date"] < release_date]
    if not pool:
        return None, None
    best = pool[-1]
    try:
        return best["date"], float(best["value"])
    except ValueError:
        return best["date"], None


def value_released_on(obs, release_date, series):
    """
    With output_type=2 each observation row looks like:
        {"date": "2026-05-01", "CPIAUCSL_20260610": "333.979", ...}
    i.e. one column per vintage (SERIES_YYYYMMDD). To get the number printed on
    `release_date` we take that vintage column and the newest period carrying it.
    Falls back to the latest vintage on/before the release date.
    """
    tag = release_date.replace("-", "")
    all_tags = sorted({k.rsplit("_", 1)[-1] for o in obs for k in o
                       if k.startswith(series + "_")})
    if not all_tags:
        return None, None
    use = tag if tag in all_tags else max((t for t in all_tags if t <= tag),
                                          default=None)
    if use is None:
        return None, None
    col = f"{series}_{use}"
    pool = [o for o in obs if o.get(col) not in (".", None, "")]
    if not pool:
        return None, None
    best = max(pool, key=lambda o: o["date"])
    try:
        return best["date"], float(best[col])
    except (ValueError, TypeError):
        return best["date"], None


def build(start, end):
    rows = []
    for rid, meta in config.MACRO_EVENTS.items():
        if rid == 101:  # FOMC: use hardcoded schedule, not FRED release dates
            dates = [d for d in config.FOMC_DATES if start <= d <= end]
        else:
            try:
                dates = release_dates(rid, start, end)
            except RuntimeError as e:
                print(f"  ! {meta['name']}: {e}", file=sys.stderr)
                continue
        # look back a bit before `start` so the first release in-window still
        # has a prior vintage to fall back on
        vint_start = (dt.date.fromisoformat(start) - dt.timedelta(days=120)).isoformat()
        try:
            obs = series_vintage(meta["series"], vint_start, end)
            plain = False
        except RuntimeError:
            # huge vintage sets (daily series over long ranges) time out --
            # fall back to latest-vintage values
            print(f"    (vintages too large for {meta['series']}; using latest values)")
            obs = series_plain(meta["series"], end)
            plain = True
        for d in dates:
            period, val = (value_plain(obs, d) if plain
                           else value_released_on(obs, d, meta["series"]))
            rows.append({
                "release_date": d,
                "report": meta["name"],
                "tier": meta["tier"],
                "release_id": rid,
                "time_et": meta["at"],
                "series": meta["series"],
                "units": meta["units"],
                "period": period,          # which month/quarter it covers
                "value": val,              # actual headline value as released
            })
        print(f"  {meta['name']:38s} {len(dates):2d} releases")
        time.sleep(0.2)

    df = pd.DataFrame(rows).sort_values(["release_date", "tier"]).reset_index(drop=True)
    # month-over-month / change vs previous print of the same report (rough
    # magnitude signal; NOT a consensus surprise)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["prev_value"] = df.groupby("report")["value"].shift(1)
    df["chg_vs_prev"] = df["value"] - df["prev_value"]
    return df


def main():
    ap = argparse.ArgumentParser()
    today = dt.date.today()
    ap.add_argument("--start", default=str(today - dt.timedelta(days=190)))
    ap.add_argument("--end", default=str(today))
    args = ap.parse_args()

    if not config.FRED_API_KEY:
        sys.exit("No FRED_API_KEY in .env")

    print(f"Fetching macro release calendar {args.start} -> {args.end} from FRED")
    df = build(args.start, args.end)
    df.to_csv(config.MACRO_CSV, index=False)
    print(f"\nWrote {len(df)} release rows -> {config.MACRO_CSV}")
    print(df[["release_date", "report", "value", "chg_vs_prev"]].tail(20).to_string(index=False))


if __name__ == "__main__":
    main()
