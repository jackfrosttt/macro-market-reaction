# CLAUDE.md — orientation for AI instances working in this repo

## ⚠️ READ FIRST — this project has a PUBLIC mirror
There are TWO GitHub repos (owner `jackfrosttt`):
- `market-data` — **PRIVATE**, full backup incl. raw price CSVs and (locally) `.env`.
- `macro-market-reaction` — **PUBLIC** portfolio repo: code + derived analysis
  only, NO raw vendor CSVs, NO `.env`, separate clean history.

**Public sync policy (user-authorized 2026-07-02):** the user wants the public
repo synced EVERY time work lands, with private stuff stripped. Use
`python run.py sync` (sync_public.py) — it copies only the allowlist (*.py,
docs, analysis/, FRED csv), hard-aborts if .env/daily_*.csv/market.db/key
material would be published. NEVER sync by hand-copying files; never bypass
its safety checks. Commit+push the PRIVATE repo first, then run sync.


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
- `brief.py` — user-facing briefing: `brief` (9am refresh+watchlist), `calendar`,
  `history` (last 5mo per report), `cheatsheet` (per-report trend/chop tendency).
- `build_db.py` — loads CSVs into local SQLite `market.db` (tables: prices,
  macro_releases, event_reactions). Command: `run.py db`.
- `fetch_intraday.py` — 30-min SPY/QQQ bars into `market.db` (intraday,
  event_intraday) to pinpoint WHEN a move happened. Command: `run.py intraday`.
  TD serves regular-hours only (no pre-market), so 8:30 reports show as the open
  gap; 10:00/14:00 reports are pinpointed exactly.
- `run.py` — entry point: `prices | macro | analyze | brief | calendar | history
  | cheatsheet | db | intraday | all`, passes through args.

## Newer modules
- `fetch_options.py` (`run.py options`) — FREE CBOE delayed chains (Twelve Data
  options = paid, don't use). P/C ratios, OI walls, ATM IV; appends to
  `options_snapshots` in market.db so positioning can be tracked over time.
- `darkpool.py` (`run.py darkpool`) — FINRA ATS weekly dark-pool volume
  (api.finra.org POST with compareFilters; weekStartDate EQUAL filter REQUIRED)
  + high-volume/no-move anomaly proxy on daily data.
- `supplemental_events.csv` — USER-maintained (comment='#' format): ISM, Fed
  minutes, sentiment + CONSENSUS numbers pasted weekly from MarketWatch.
  Merged everywhere via `analyze.load_events()`; surprise = actual − consensus.
  This is the user's workflow — remind them to fill it weekly, don't overwrite it.

## Remaining blind spots (be honest about these)
- Consensus/surprise now possible but MANUAL (user fills supplemental CSV).
- ISM etc. covered only via the manual CSV — not auto-fetched.
- No Fed-speaker calendar. No pre-market/futures (only the resulting open gap).
- FINRA dark-pool data lags 2-4 weeks. Options data is delayed ~15 min.
- Intraday is SPY/QQQ only. Correlation != causation (see Jun 11 PPI bounce).

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
