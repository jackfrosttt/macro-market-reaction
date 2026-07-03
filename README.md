# Macro-Release → Market-Reaction Analyzer

**Which macroeconomic report releases actually move the market in a clean,
tradable direction — and which just create a wide, choppy day that closes where
it started?**

A Python data pipeline that pulls U.S. macro report releases (CPI, jobs report,
FOMC, PPI, PCE, retail sales, GDP, JOLTS, jobless claims) from **FRED**, pulls
daily price data for SPY/QQQ from **Twelve Data**, and quantifies each release
day as **DIRECTIONAL** (a one-way move you can ride with options) vs **CHOP**
(wide range that round-trips and bleeds option premium).

Built to answer a real trading question: *if I'm buying directional options, which
release days are worth trading and which are traps?*

---

## Sample output

```
[1] BASELINE  (average absolute reaction)
                         n  |ret_cc|    range  trend_eff  %directional
macro-release days      26     0.87%    1.17%       0.57           42%
normal days             58     0.67%    1.06%       0.41           22%

[2] PER-REPORT REACTION  (SPY, ranked by avg |ret_cc|)
report                              n  |ret_cc|  |ret_oc|   range  trend  dir%
PPI (Producer Price Index)          4     1.22%     0.94%   1.39%   0.71   75%
Jobs Report (NFP + Unemployment)    4     1.21%     0.71%   1.30%   0.50   50%
JOLTS (Job Openings)                5     1.04%     0.84%   1.15%   0.70   60%
...
CPI (Consumer Price Index)          4     0.48%     0.43%   1.06%   0.38   25%
```

**Finding:** macro-release days are ~30% more likely to trend than normal days,
but it's report-specific — e.g. in this window PPI and the jobs report produced
clean directional moves, while CPI mostly chopped. The full day-by-day log tags
each release day (see `analysis/report.md`).

---

## Design highlights

- **Vendor resilience:** started on yfinance, which now returns HTTP 429 and
  stale bars — swapped the price feed to Twelve Data with rate-limit-aware
  batching (free tier: 8 req/min).
- **Point-in-time correctness:** macro values are pulled from FRED's *vintage*
  API (`output_type=2`) so each number is the value **as printed on its release
  date**, not a later revision — avoiding look-ahead bias.
- **The core metric:** `trend_eff = |ret_oc| / range_pct` — the share of the
  day's high-to-low range that survives as net directional move. High = trend,
  low = chop. This is what separates a tradable day from a trap.
- **Honest scope:** free data gives *actuals*, not *consensus* — so the tool
  measures realized reaction, not the surprise. Documented, not hand-waved.

## Metrics

| metric      | meaning                                                        |
|-------------|----------------------------------------------------------------|
| `gap`       | open vs prior close — overnight reaction to 8:30am data         |
| `ret_cc`    | close vs prior close — full day's move                          |
| `ret_oc`    | close vs open — move if you enter at the open                   |
| `range_pct` | (high − low)/prior close — how much it thrashed around          |
| `close_loc` | where it closed in the range: 1=highs, 0=lows, .5=mid           |
| `trend_eff` | \|ret_oc\| / range_pct — **trend vs chop discriminator**        |

---

## Run it yourself

Needs free API keys: [FRED](https://fredaccount.stlouisfed.org/apikeys) and
[Twelve Data](https://twelvedata.com/pricing).

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# put your keys in .env (gitignored):
#   FRED_API_KEY=...
#   TWELVE_DATA_API_KEY=...

python run.py all --days 120        # fetch prices + macro, then analyze
```

> Raw vendor price CSVs are **not** included in this repo (Twelve Data / Yahoo
> terms). `run.py prices` fetches them fresh into `daily_<SYM>.csv`.

## Files

| file                 | role                                              |
|----------------------|---------------------------------------------------|
| `fetch_prices.py`    | daily OHLC via Twelve Data                         |
| `fetch_macro.py`     | macro release dates + actuals via FRED (vintages)  |
| `analyze.py`         | metrics, day classification, per-report ranking    |
| `run.py`             | single entry point (`prices` / `macro` / `analyze` / `all`) |
| `config.py`          | keys, tickers, macro-report map                    |
| `analysis/`          | generated report + rankings (committed as a sample) |
| `macro_releases.csv` | FRED macro calendar (public-domain gov data)       |

---

*Built as an AI-directed project: I owned the trading thesis, data-source
selection, and architecture, and pair-programmed the implementation with Claude
(Anthropic). See `CLAUDE.md` for the agent-facing design notes.*
