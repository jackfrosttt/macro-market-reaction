import yfinance as yf, pandas as pd
START = "2015-01-01"
TICKERS = [
 "SPY","QQQ","IWM","DIA","RSP",                                  # broad market
 "XLK","XLF","XLE","XLV","XLI","XLY","XLP","XLB","XLU","XLRE","XLC", # 11 sectors
 "^VIX","^VIX9D","^VIX3M","^VVIX","^SKEW",                       # vol complex
 "SOXL","SOXS","TQQQ","SQQQ","SPXL","SMH",                       # leverage/semis you trade
 "NVDA","AMD","MU","GOOGL","AAPL","CRWD",                        # single names
 "^TNX","TLT","HYG","UUP","GLD",                                # rates/credit/dollar/gold
]
frames=[]
for t in TICKERS:
    try:
        df = yf.download(t, start=START, auto_adjust=False, progress=False)
        if df is None or df.empty: print("WARN none:", t); continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.reset_index(); df["Ticker"]=t
        df.to_csv(f"daily_{t.replace('^','')}.csv", index=False)
        frames.append(df); print(f"{t}: {len(df)} rows")
    except Exception as e: print("ERR", t, e)
if frames:
    alld = pd.concat(frames, ignore_index=True)
    alld.to_csv("daily_ALL.csv", index=False)
    print("\n==> combined daily_ALL.csv:", len(alld), "rows — upload THIS one")
