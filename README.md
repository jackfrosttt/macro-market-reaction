# market-data

**What this project is for (the one-liner):**
Figure out which U.S. macroeconomic report releases (CPI, jobs report, FOMC,
PPI, PCE, retail sales, etc.) tend to cause a **big, clean, one-directional
move** in the market (SPY / QQQ) versus a **wide but choppy day that closes
where it started** — so you can pick which release days are worth trading
directional options and skip the chop.

You trade options, so you want *directional* days (a move you can ride), not
*range* days (wide high-to-low swing that round-trips and bleeds premium).

---

## The idea in one picture

A macro report drops (usually 8:30am ET). Two things can happen:

- **DIRECTIONAL day** — market picks a direction and trends. Closes near the
  high or the low. Good for buying calls/puts. *(e.g. Jun 5 jobs report: SPY
  −2.58%, closed at the lows.)*
- **CHOP day** — big high-to-low range, lots of movement, but it reverses and
  closes back in the middle. Kills option premium. *(e.g. Jul 2 jobs report:
  SPY thrashed 1.5% but closed −0.13%, mid-range.)*

The analysis measures every macro-release day and tags it, then ranks each
report type by how big and how *clean* its moves usually are.

---

## Every time: open a terminal and run these two lines first

```bash
cd ~/market-data
source venv/bin/activate            # turns on the Python environment (do this once per terminal)
```

You'll know it worked when your prompt shows `(venv)`.

---

## ⭐ Your 9am Monday routine (the one command to remember)

```bash
python run.py brief
```

This does everything for the morning in one shot:
1. **refreshes** SPY/QQQ/IWM/DIA prices from Twelve Data (takes ~25s),
2. prints **what macro releases are coming this week** and tags each
   `USUALLY TRENDS` / `mixed` / `usually chops`,
3. shows **how the last 8 macro days actually reacted** (directional vs chop),
4. prints the **per-report cheat sheet** so you can see at a glance which
   reports are worth trading directionally.

Reports tagged **`<-- WATCH` / USUALLY TRENDS** are your directional-option days.

> In a hurry / market's not open yet and you don't need fresh prices?
> `python run.py brief --no-refresh` (skips the price download, instant).

---

## The other ready-made commands

| Command | What it answers |
|---------|-----------------|
| `python run.py brief` | **the morning briefing** (refresh + everything below) |
| `python run.py calendar` | *"what's releasing soon and is it usually directional?"* |
| `python run.py history` | *"show me the last 5 months of every report and how SPY reacted"* |
| `python run.py cheatsheet` | *"which reports usually TREND vs CHOP?"* |
| `python run.py analyze` | full day-by-day analysis + baseline stats |
| `python run.py db` | load everything into a local SQLite database (`market.db`) |
| `python run.py intraday` | pull 30-min bars so you can see *what time* the move happened |
| `python run.py patterns` | mine the intraday data: when do big moves happen, trend vs fade |
| `python run.py options` | free CBOE options snapshot: put/call ratio, OI walls, ATM IV |
| `python run.py darkpool` | FINRA dark-pool volume + quiet-accumulation scan |
| `python run.py backtest` | do the patterns make money? tested rules with win rates |
| `python run.py sync` | push code+analysis to the public portfolio repo (strips private) |
| `python run.py btc` | **is Bitcoin trending up or down right now?** live 15-min verdict + context |
| `python run.py q list` | **the 50-query library** — premade answers to "is this something?" |

## ❓ The query library (`run.py q ...`)

50 premade questions, grouped. `python run.py q list` shows all of them. The ones
you'll use most:

```bash
python run.py q today                # is today/yesterday SOMETHING? (SPY QQQ IWM BTC one-shot)
python run.py q btc                  # is bitcoin trending up or down RIGHT NOW (live)
python run.py q move-z QQQ           # how rare was that move?
python run.py q after-down2          # what usually happens the day after -2%?
python run.py q report Jobs          # full history of any report vs SPY/QQQ
python run.py q event-league         # which reports move markets most (2.5y)
python run.py q worst-chops          # the option-killer days to learn from
python run.py q fomc-cycle           # SPY day before/of/after every FOMC
python run.py q em SPY 5             # expected move next 5 days (1-sigma range)
python run.py q day 2026-06-17       # 30-min replay of any day + what released
python run.py q btc-spy              # is BTC trading with stocks (macro-driven)?
python run.py q formulas             # the full formula reference card
```

Queries take an optional symbol (`q rsi NVDA`), and `q breakeven 750 3.50 call`
computes option breakevens. If you're wondering "is X something?" — check
`q list` first; it's probably premade.

### Placeholders you can change (the `--flags`)

```bash
python run.py calendar --days 14        # look further ahead (default 10)
python run.py history  --months 5       # how far back per report (default 5)
python run.py cheatsheet --months 3     # tendency over a shorter window
python run.py analyze --days 120        # analysis window in days
python run.py analyze --tier 1          # ONLY top movers (CPI/NFP/FOMC/PCE)
python run.py analyze --symbol QQQ      # analyze QQQ instead of SPY
python run.py prices --all              # refresh the full ticker list (slow)
python run.py macro --start 2026-02-01 --end 2026-07-02   # rebuild calendar for a date range
```

Anything printed is also saved to `analysis/` (`report.md`, `report_ranking.csv`,
`daily_metrics.csv`) so you can reopen it later without re-running.

---

## If you'd rather just ask Claude (copy-paste prompts)

Open this folder in Claude Code and paste any of these:

- `Run the morning brief and tell me which days this week are worth trading directional options.`
- `Pull the last 5 months of the jobs report and CPI and tell me which were directional and why.`
- `What macro is out this week, and based on history which day is most likely to be a big directional move (not chop)?`
- `Refresh prices and show me how QQQ reacted to the last 3 FOMC days.`
- `Add ISM Manufacturing and ISM Services to the pipeline.` *(ISM isn't on FRED — see "Known limitation")*

---

## What each metric means

| metric      | meaning                                                        |
|-------------|----------------------------------------------------------------|
| `gap`       | open vs prior close — the overnight reaction to 8:30am data     |
| `ret_cc`    | close vs prior close — the full day's move                      |
| `ret_oc`    | close vs open — the move if you enter at the open               |
| `range_pct` | (high − low)/prior close — how much it thrashed around          |
| `close_loc` | where it closed in the day's range: 1=at highs, 0=at lows, .5=mid |
| `trend_eff` | \|ret_oc\| / range_pct — **the key one.** High = trend, low = chop |

**Reading it:** a report you want to trade has a big `|ret_cc|`, a high
`trend_eff`, and a high directional %. A report that's mostly a trap has a big
`range` but a *low* `trend_eff` (wide and whippy).

---

## Files

| file                  | what it does                                             |
|-----------------------|---------------------------------------------------------|
| `config.py`           | API keys (from `.env`), ticker list, macro-report map   |
| `fetch_prices.py`     | pull daily OHLC from **Twelve Data** (reliable, current) |
| `fetch_macro.py`      | pull macro **release dates + actual values** from **FRED** |
| `analyze.py`          | the release-vs-reaction analysis & day-by-day log        |
| `run.py`              | single entry point that ties the above together          |
| `dump_daily.py`       | legacy yfinance dumper (kept; Yahoo now rate-limits)     |
| `daily_<SYM>.csv`     | daily price history per ticker                           |
| `macro_releases.csv`  | the macro calendar with actual values                    |
| `analysis/`           | generated report + CSVs                                  |
| `.env`                | your API keys — **gitignored, never commit**             |

---

## 🧭 FIELD GUIDE: how to interpret what you see (no AI needed)

Work through this in order on any morning:

**1. `python run.py brief` — is today an event day?**
- No tier-1/2 event → expect chop; the backtest says opening gaps on quiet days
  historically FADE (reverse). Don't chase the open.
- Tier-1 event (Jobs/CPI/FOMC/PCE) → keep reading.

**2. `python run.py options` — what's priced in?**
- ATM IV says how big a move options are paying for. Rule of thumb: if the
  "~%/day" number is SMALLER than what that report usually moves (see
  `cheatsheet`), directional options are cheap. If bigger, the move is already
  paid for and you need to be MORE right.
- A giant OI wall at one strike near spot + expiry this week = pin risk;
  price tends to gravitate there. Directional trades fight the pin.
- Put/call volume >1.1 = crowd already hedged (surprises hurt less);
  <0.7 = complacent (bad news hits harder).

**3. The release itself — three questions decide direction:**
- What was CONSENSUS? (your `supplemental_events.csv` / MarketWatch) — the move
  comes from actual vs consensus, not the number itself.
- What's the market's CURRENT FEAR? Inflation regime: hot CPI = down. Growth
  scare: weak jobs = down, and even "good" inflation news can't rally it.
- Does the print CONFIRM the fear? Confirm = clean trend more likely.
  Contradict = fight between shorts covering and doubters = chop risk.

**4. Timing rules (from `patterns` + `backtest`, drilled into the data):**
- 9:30–10:00 is the most violent 30 minutes; 40% of days set their high or
  low there. 8:30 reports express themselves in this window.
- The 8:30 knee-jerk gap is a COIN FLIP overall — only jobs-report gaps have
  historically been worth following (67% win). CPI/FOMC gaps: weak edge. PCE:
  historically the gap FADED.
- 10:00 reports (ISM, JOLTS): the reaction bar is 10:00–10:30.
- FOMC: the entire move happens after 2:00pm. Do not pre-position.
- Once a macro day picks a direction by late morning, it tends to HOLD into
  the close (trend); quiet days mean-revert (fade).
- 12:00–1:30 is dead. Power hour (3–4pm) is the second wind.

**5. After the fact — was it directional? (`analyze` / `history`)**
- `trend_eff` ≥ ~0.6 and closed near high/low = clean day; the report "worked".
- Big range but `trend_eff` < 0.45 = chop — log WHICH report did that and
  check `cheatsheet`: some reports are habitual choppers (CPI lately).

**Red flags that a "reaction" is fake:** move started BEFORE the release
(check `intraday` table), or the market was already stretched (an oversold
bounce on a bad-news day is positioning, not the data — e.g. Jun 11 PPI).

## 📝 Your weekly 2-minute job: `supplemental_events.csv`

This is how YOU feed the tool the data it can't get for free — **ISM, Fed
minutes, consumer sentiment, and (most important) the CONSENSUS forecast**:

1. Open the MarketWatch economic calendar (or Investing.com).
2. Open `supplemental_events.csv` (any text editor, or `open supplemental_events.csv`).
3. Add one row per report: date, name, time, tier, **consensus**, blank actual, previous.
4. After a release, fill in the **actual**.
5. Run `python run.py db` — it computes the **surprise** (actual − consensus),
   which is the thing markets really react to.

Rows you add show up automatically in `calendar` and `brief` marked with `*`.
Don't duplicate reports FRED already tracks (CPI, PPI, jobs, retail sales,
claims, GDP, PCE, JOLTS) — only add what's missing, plus consensus numbers.

## Options data (`python run.py options`)

Free delayed chain from CBOE (Twelve Data options need a paid plan — not needed).
How to read it:
- **put/call volume ratio** — >1.1 = fear (put-heavy), <0.7 = greed. Today's flow.
- **put/call OI ratio** — standing positioning, slower-moving.
- **OI walls** — strikes with huge open interest act like magnets/pins near
  expiry; a giant wall at one strike right at spot often means price gets
  "pinned" there into that expiry.
- **ATM IV → ~%/day** — how big a daily move options are pricing. If a macro
  day is coming and this looks small, options are cheap for a directional bet;
  if huge, the move is already paid for.

Run it daily — snapshots accumulate in `market.db` (`options_snapshots`) so you
can see positioning shift into an event.

## Dark money (`python run.py darkpool`)

Two honest, free views (real institutional-flow feeds cost money):
- **FINRA ATS weekly** (official dark-pool volume, ~2–4 week publication delay):
  watch the **share%** column vs its own average. Elevated share while price
  falls = possible stealth accumulation; into strength = possible distribution.
- **Volume-anomaly proxy** (no delay, from our own data): days with huge volume
  but no price movement — the footprint of someone absorbing shares quietly.

These are *footprints, not proof*. Use them as a tiebreaker, never a signal.

## Local database (`market.db`)

`python run.py db` loads everything into a single SQLite file you can query with
plain SQL or a GUI like [DB Browser for SQLite](https://sqlitebrowser.org).

Tables: `prices`, `macro_releases`, `event_reactions` (daily reaction + class per
release), plus `intraday` and `event_intraday` after you run
`python run.py intraday`.

Example queries:
```bash
# every clean directional macro day
sqlite3 -header -column market.db \
  "SELECT date, report, ROUND(spy_ret_cc*100,2) spy, spy_class FROM event_reactions WHERE spy_class='DIRECTIONAL' ORDER BY date;"

# what TIME did the move happen on FOMC days?
sqlite3 -header -column market.db \
  "SELECT date, window, ROUND(window_move*100,2) react, ROUND(day_move*100,2) day FROM event_intraday WHERE report LIKE 'FOMC%' AND ticker='SPY';"

# the intraday path of any day
sqlite3 -header -column market.db \
  "SELECT substr(dt,12,5) time, close FROM intraday WHERE ticker='SPY' AND dt LIKE '2026-06-17%' ORDER BY dt;"
```

## Data sources

- **Twelve Data** (prices) — free tier, 8 requests/min, 800/day. Chosen because
  Yahoo/yfinance now returns HTTP 429 and stale bars.
- **FRED** (macro) — free, gives official release dates and the actual headline
  value for each report.

## Known limitation (read this)

FRED and the free Twelve Data tier give the **actual** released number but **not
the consensus/expected** number. Markets react to the *surprise* (actual vs
expected), so this tool measures the **reaction** (price action) directly rather
than the surprise. If you want true surprise data, you'd add a paid economic-
calendar feed (Twelve Data premium, Trading Economics, etc.) — see
`config.MACRO_EVENTS` for where reports are defined.

The `chg_vs_prev` column in `macro_releases.csv` is this report vs its *previous
print* — a rough magnitude signal, **not** a consensus surprise.
