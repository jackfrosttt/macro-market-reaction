"""
sync_public.py -- push the shareable parts of this project to the PUBLIC
portfolio repo (github.com/jackfrosttt/macro-market-reaction), stripping
everything private.

ALLOWED : *.py, README.md, CLAUDE.md, requirements.txt, .gitignore,
          supplemental_events.csv (calendar entries, no secrets),
          macro_releases.csv (FRED = public domain), analysis/ outputs
BLOCKED : .env (API keys!), daily_*.csv (vendor price data), market.db,
          options_*.csv, venv/

Usage:  python run.py sync
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import config

PUBLIC_REPO = "https://github.com/jackfrosttt/macro-market-reaction.git"
ALLOW_FILES = ["README.md", "CLAUDE.md", "requirements.txt", ".gitignore",
               "supplemental_events.csv", "macro_releases.csv"]
BLOCK_NAMES = {".env", "market.db"}


def sh(*cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pubsync_"))
    print(f"Cloning public repo -> {tmp}")
    sh("git", "clone", "--depth", "1", PUBLIC_REPO, str(tmp))

    # copy allowlist
    copied = []
    for py in sorted(config.ROOT.glob("*.py")):
        shutil.copy2(py, tmp / py.name); copied.append(py.name)
    for name in ALLOW_FILES:
        src = config.ROOT / name
        if src.exists():
            shutil.copy2(src, tmp / name); copied.append(name)
    (tmp / "analysis").mkdir(exist_ok=True)
    for f in (config.ROOT / "analysis").glob("*"):
        shutil.copy2(f, tmp / "analysis" / f.name); copied.append(f"analysis/{f.name}")

    # hard safety check: nothing private in the clone
    bad = [p for p in tmp.rglob("*")
           if p.name in BLOCK_NAMES
           # raw vendor OHLC lives at repo root; analysis/daily_metrics.csv is
           # our own derived output and is fine to publish
           or (p.name.startswith("daily_") and p.suffix == ".csv"
               and p.parent.name != "analysis")
           or (p.name.startswith("options_") and p.suffix == ".csv")]
    if bad:
        sys.exit(f"ABORT -- private files would be published: {bad}")
    # grep for the REAL key values (from .env via config) -- catches any leak
    # regardless of variable name, and can't false-positive on this script
    for secret in [config.FRED_API_KEY, config.TWELVE_DATA_API_KEY]:
        if not secret:
            continue
        leaked = subprocess.run(["grep", "-rl", secret, str(tmp)],
                                capture_output=True, text=True).stdout.strip()
        if leaked:
            sys.exit(f"ABORT -- key material found in: {leaked}")

    sh("git", "add", "-A", cwd=tmp)
    if not sh("git", "status", "--porcelain", cwd=tmp):
        print("Public repo already up to date."); return
    sh("git", "-c", "user.name=jackfrosttt",
       "-c", "user.email=paid_retort0@icloud.com",
       "commit", "-m", "Sync from private working repo (code + derived analysis only)",
       cwd=tmp)
    sh("git", "push", "origin", "HEAD:main", cwd=tmp)
    print(f"Synced {len(copied)} files to PUBLIC repo. Verified: no keys, no vendor data.")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
