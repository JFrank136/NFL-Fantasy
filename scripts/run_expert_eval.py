#!/usr/bin/env python
"""Weekly expert-accuracy evaluation + shadow weights (src/expert_eval/).

    python scripts/run_expert_eval.py                  # evaluate every finalized week of the current season
    python scripts/run_expert_eval.py --weeks 9        # one week (skipped if its games aren't all final)
    python scripts/run_expert_eval.py --backtest       # walk-forward backtest from the stored evidence
    python scripts/run_expert_eval.py --local-only     # no Supabase; CSV mirror only (dry run / offline)

Idempotent: reruns upsert on natural keys and never delete. Shadow only -- nothing here
changes the live Rankings page. See docs/EXPERT_EVAL.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.expert_eval import pipeline
from src.expert_eval.backtest import backtest
from src.expert_eval.store import Store
from src import season_config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--weeks", type=int, nargs="*")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--local-only", action="store_true")
    a = ap.parse_args()
    season = a.season or getattr(season_config, "SEASON", None) or 2026
    store = Store(local_only=a.local_only)
    if a.backtest:
        backtest(store, season)
        return 0
    out = pipeline.run(season, weeks=a.weeks, store=store)
    print(json.dumps({k: v for k, v in out.items() if k != "info"}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
