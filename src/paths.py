"""Where the big append-only pull outputs live.

data/raw and data/processed grow with every pull (the rankings CSV is 130 MB+)
and sat inside OneDrive, where a sync-state glitch left rankings_long.csv
rejecting writes (OSError 22) and silently broke the weekly pull. They now live
outside OneDrive. Override with the FANTASY_DATA_DIR env var; if the external
folder doesn't exist (fresh checkout), falls back to the repo's data/ folder.
Small runtime files (status JSON, logs, push state) stay in the repo's data/.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_EXTERNAL = Path(os.environ.get("FANTASY_DATA_DIR") or Path.home() / "FantasyData" / "in-season")
DATA_ROOT = _EXTERNAL if _EXTERNAL.is_dir() else BASE_DIR / "data"

RAW_DIR = DATA_ROOT / "raw"
PROCESSED_DIR = DATA_ROOT / "processed"
