# CLAUDE.md — orientation for AI instances working in this repo

## Purpose
Correlate U.S. macroeconomic **report releases** with **market reaction** in
SPY/QQQ to find which releases produce big **directional** moves (tradable with
directional options) vs **chop** (wide range, closes mid, bad for premium).
The user trades options and wants to trade only high-directional-conviction
release days.

## Architecture (all plain Python, venv in ./venv)
- `config.py` — loads `.env` (hand-rolled parser, no python-dotenv), defines
  `CORE_SYMBOLS`, `ALL_SYMBOLS`, `MACRO_EVENTS` (keyed by FRED release_id), and
  `FOMC_DATES` (hardcoded — FRED release 101 returns junk daily dates).
- `fetch_prices.py` — Twelve Data daily OHLC. Yahoo/yfinance is dead (429), do
  NOT reintroduce it as the primary source. Writes `daily_<SYM>.csv` keeping the
  yfinance-era schema (Date, Adj Close, Close, High, Low, Open, Volume, Ticker).
  Merges: old history before the fresh window is kept; recent window overwritten
  with Twelve Data so the analysis period is single-source.
- `fetch_macro.py` — FRED. Uses `release/dates` (query param `release_id`, NOT a
  path segment) + `series/observations` with `output_type=2` (all vintages).
  Vintage columns look like `CPIAUCSL_20260610`; `value_released_on()` parses the
  `SERIES_YYYYMMDD` suffix to get the number printed on a given release date.
  Writes `macro_releases.csv`.
- `analyze.py` — computes per-day metrics (see below), classifies each day, ranks
  reports, writes `analysis/{report.md,report_ranking.csv,daily_metrics.csv}`.
- `run.py` — entry point: `prices | macro | analyze | all`, passes through args.

## Key metric
`trend_eff = |ret_oc| / range_pct` is the trend-vs-chop discriminator.
Day classes: DIRECTIONAL (real net move + high trend_eff), CHOP (wide range +
low trend_eff), QUIET (tiny range), MIXED (everything else). Thresholds are
constants at the top of `analyze.py`.

## Important constraints / gotchas
- **No consensus/surprise data.** FRED + free Twelve Data give ACTUALS only.
  We measure reaction (price), not surprise. Don't claim surprise correlation.
- Free Twelve Data tier: 8 req/min, 800/day — `fetch_prices.py` sleeps 8s
  between calls. Don't hammer it.
- `.env` holds real API keys and is gitignored. Never print or commit it.
- Env python is 3.14, pandas 3.x — avoid deprecated pandas APIs.
- GDP and PCE (Personal Income & Outlays) release the same day in this data, so
  their per-report stats come out identical; that's expected, not a bug.

## Typical run
```bash
source venv/bin/activate
python run.py all --days 120        # refresh everything + analyze last 120d
```

## Possible next steps (not yet built)
- Intraday reaction windows via Twelve Data `time_series` interval=15min/30min
  around the release time (esp. 8:30 reports & 2pm FOMC) for finer trend/chop.
- A real economic-calendar feed for consensus → true surprise vs reaction.
- Extend the window (analyze.py --days) once more price history is TD-sourced.
