"""
Central configuration for the market-data project.

Loads API keys from .env (no external deps) and defines:
  - which tickers we track,
  - which macro reports (FRED "releases") we care about, and how to read
    the headline number for each.

Nothing here hits the network. Import it from the fetch/analyze scripts.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# .env loading (tiny hand-rolled parser so we need no python-dotenv dependency)
# ---------------------------------------------------------------------------
def load_env(path: Path = ROOT / ".env") -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_ENV = load_env()
FRED_API_KEY = _ENV.get("FRED_API_KEY", "")
TWELVE_DATA_API_KEY = _ENV.get("TWELVE_DATA_API_KEY", "")


# ---------------------------------------------------------------------------
# Tickers.  The ones the analysis actually needs are CORE_SYMBOLS; the wider
# list is what dump_daily.py / fetch_prices.py can refresh on request.
# ---------------------------------------------------------------------------
CORE_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA"]

# Twelve Data uses plain symbols for these ETFs/stocks. Index symbols like VIX
# are not on the free tier, so we keep the equity/ETF universe here.
ALL_SYMBOLS = [
    "SPY", "QQQ", "IWM", "DIA", "RSP",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE", "XLC",
    "SOXL", "SOXS", "TQQQ", "SQQQ", "SPXL", "SMH",
    "NVDA", "AMD", "MU", "GOOGL", "AAPL", "CRWD",
    "TLT", "HYG", "UUP", "GLD",
]


# ---------------------------------------------------------------------------
# Macro reports we track.  Keyed by FRED release_id.
#   name   : human label
#   tier   : 1 = top market-mover, 2 = important, 3 = secondary
#   series : FRED series_id whose latest value is the "headline" number
#   units  : how to read that series value (for the report, not consensus)
#   at     : approximate release time (ET) -- helps interpret gap vs intraday
# FRED gives us the ACTUAL value + the official release DATE. It does NOT give
# the consensus/expected estimate, so "surprise" is not computed here (see
# README). Market reaction is measured purely from price action.
# ---------------------------------------------------------------------------
MACRO_EVENTS = {
    50:  {"name": "Jobs Report (NFP + Unemployment)", "tier": 1,
          "series": "PAYEMS", "units": "payrolls level (k)", "at": "08:30"},
    10:  {"name": "CPI (Consumer Price Index)",        "tier": 1,
          "series": "CPIAUCSL", "units": "index (headline)", "at": "08:30"},
    54:  {"name": "PCE (Personal Income & Outlays)",   "tier": 1,
          "series": "PCEPILFE", "units": "core PCE index", "at": "08:30"},
    101: {"name": "FOMC Rate Decision",                "tier": 1,
          "series": "DFEDTARU", "units": "fed funds upper %", "at": "14:00"},
    46:  {"name": "PPI (Producer Price Index)",        "tier": 2,
          "series": "PPIFIS", "units": "final demand index", "at": "08:30"},
    9:   {"name": "Retail Sales (Advance)",            "tier": 2,
          "series": "RSAFS", "units": "$M sales", "at": "08:30"},
    53:  {"name": "GDP",                               "tier": 2,
          "series": "A191RL1Q225SBEA", "units": "real GDP QoQ % ann.", "at": "08:30"},
    192: {"name": "JOLTS (Job Openings)",              "tier": 2,
          "series": "JTSJOL", "units": "openings level (k)", "at": "10:00"},
    180: {"name": "Initial Jobless Claims",            "tier": 3,
          "series": "ICSA", "units": "claims", "at": "08:30"},
}

# FOMC decision dates are hardcoded: FRED's "FOMC Press Release" release (id
# 101) lists junk daily dates, so we use the Fed's published 2026 schedule
# (announcement day = 2nd day of each two-day meeting).
FOMC_DATES = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Data file locations
PRICE_DIR = ROOT
MACRO_CSV = ROOT / "macro_releases.csv"
SUPPLEMENTAL_CSV = ROOT / "supplemental_events.csv"   # manual: ISM, consensus...
ANALYSIS_DIR = ROOT / "analysis"
