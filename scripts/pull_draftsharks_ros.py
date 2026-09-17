#!/usr/bin/env python
"""Pulls Draft Sharks' rest-of-season (ROS) rankings for both scoring
formats and writes them to data/raw/draftsharks_ros/ (immutable snapshot)
and data/processed/ros_rankings_long.csv (append).

Usage:
    python scripts/pull_draftsharks_ros.py                  # both scorings, current week snapshot
    python scripts/pull_draftsharks_ros.py --scoring half-ppr
    python scripts/pull_draftsharks_ros.py --as-of-week 3    # override the snapshot week marker

Exits non-zero only on a validation error or unexpected failure. Writes
data/last_draftsharks_ros_status.json using the same
{run_at, ok, combos: {"week{N}/draftsharks_ros/{scoring}": status}} shape
last_run_status.json already uses, so scheduled_pull.ps1's existing dynamic
source-discovery logic can pick this file up as another source with no
hardcoded label added to the PowerShell script.
"""

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import normalize, season_config, storage, validate
from src.sources.draftsharks_ros import DraftSharksRosFetchError, fetch_draftsharks_ros

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "ros_rankings_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_draftsharks_ros_status.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=season_config.SEASON)
    parser.add_argument("--scoring", default="half-ppr,ppr", help="Comma list")
    parser.add_argument(
        "--as-of-week", type=int, default=None,
        help="Defaults to the current active week (src/season_config.py).",
    )
    args = parser.parse_args()

    as_of_week = args.as_of_week if args.as_of_week is not None else season_config.current_week()
    scorings = args.scoring.split(",")

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(f"Starting Draft Sharks ROS pull -- as-of week {as_of_week}, scorings {scorings}")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    run_status = {}
    any_errors = False
    success_count = 0

    for i, scoring in enumerate(scorings, 1):
        status_key = f"week{as_of_week}/draftsharks_ros/{scoring}"
        print(f"[{i}/{len(scorings)}] {scoring}...")
        try:
            raw = fetch_draftsharks_ros(scoring_slug=scoring)
        except DraftSharksRosFetchError as e:
            print(f"\n[FAILED] {scoring}: {e}")
            any_errors = True
            run_status[status_key] = f"failed: {e}"
            continue
        except Exception as e:
            print(f"\n[FAILED] Unexpected failure on {scoring}: {e}")
            traceback.print_exc()
            run_status[status_key] = f"failed: unexpected error: {e}"
            _write_status(run_status, any_errors=True)
            sys.exit(1)

        rows = normalize.draftsharks_ros_to_rows(raw, args.season, as_of_week, scoring, pulled_at)
        rows, dedupe_issues = validate.dedupe_players(rows)
        issues = dedupe_issues + validate.validate_ros_rankings(rows)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"   [{tag}] {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[status_key] = "failed: " + "; ".join(
                i.message for i in issues if i.severity == "error"
            )
            print(f"   Not writing output for {scoring} -- validation failed.")
            continue

        snapshot_path = storage.ros_raw_snapshot_path(
            RAW_DIR / "draftsharks_ros", "draftsharks", args.season, as_of_week, scoring, pulled_at
        )
        storage.write_raw_snapshot(snapshot_path, raw)
        storage.append_ros_rankings_processed(PROCESSED_PATH, rows)
        run_status[status_key] = "ok"
        success_count += 1
        print(f"   {len(rows)} rows -> {snapshot_path.relative_to(BASE_DIR)}")

    elapsed = datetime.now() - start
    mins, secs = elapsed.seconds // 60, elapsed.seconds % 60
    print(f"\n{'=' * 45}")
    print(f"Done: {success_count}/{len(scorings)} scoring format(s) written")
    print(f"Time: {mins}m {secs}s")
    print(f"Processed output: {PROCESSED_PATH.resolve()}")
    print(f"{'=' * 45}")

    _write_status(run_status, any_errors=any_errors)
    if any_errors:
        sys.exit(1)


def _write_status(run_status: dict, any_errors: bool = True) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ok": not any_errors,
                "combos": run_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
