#!/usr/bin/env python
"""Pulls Justin Boone's rest-of-season trade value charts (QB/RB/WR/TE) for
the current week and writes them to data/raw/boone_trade_values/ (immutable
snapshot) and data/processed/trade_values_long.csv (append).

Usage:
    python scripts/pull_trade_values.py               # current week, all 4 positions
    python scripts/pull_trade_values.py --week 2       # force a specific week
    python scripts/pull_trade_values.py --position rb,wr

A position not yet published for the target week is skipped (not an error --
see src/sources/boone_trade_values.py). Exits non-zero only on a validation
error or unexpected failure. Writes data/last_trade_values_status.json
(position -> ok|failed: <reason>|not_yet_published) so an external check
(scheduled_pull.ps1) can tell success from failure without parsing console
text.
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
from src.sources.boone_trade_values import (
    POSITIONS,
    BooneTradeValueFetchError,
    discover_position_urls,
    fetch_position_trade_values,
)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "trade_values_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_trade_values_status.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, default=None, help="Defaults to the current active week.")
    parser.add_argument("--season", type=int, default=season_config.SEASON)
    parser.add_argument("--position", default="all", help="Comma list (qb,rb,wr,te), or 'all'")
    args = parser.parse_args()

    week = args.week if args.week is not None else season_config.current_week()
    wanted_positions = (
        POSITIONS if args.position == "all"
        else [p.strip().upper() for p in args.position.split(",")]
    )

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(f"Starting Boone trade-value pull -- week {week}, positions {wanted_positions}")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    try:
        urls = discover_position_urls(week)
    except BooneTradeValueFetchError as e:
        print(f"\n[FAILED] Could not discover this week's article URLs: {e}")
        _write_status({p: f"failed: could not discover URLs: {e}" for p in wanted_positions})
        sys.exit(1)

    run_status = {}
    any_errors = False
    success_count = 0

    for i, position in enumerate(wanted_positions, 1):
        print(f"[{i}/{len(wanted_positions)}] {position}...")
        if position not in urls:
            print("   Not yet published for this week -- skipping.")
            run_status[position] = "not_yet_published"
            continue

        url = urls[position]
        try:
            table_rows = fetch_position_trade_values(position, url)
        except BooneTradeValueFetchError as e:
            print(f"\n[FAILED] {position}: {e}")
            any_errors = True
            run_status[position] = f"failed: {e}"
            continue
        except Exception as e:
            print(f"\n[FAILED] Unexpected failure on {position}: {e}")
            traceback.print_exc()
            run_status[position] = f"failed: unexpected error: {e}"
            _write_status(run_status, any_errors=True)
            sys.exit(1)

        # Normalize before validating -- validate_trade_values expects TradeValueRow objects.
        # This order must stay fixed: normalize -> validate -> write raw snapshot + CSV.
        rows = normalize.boone_trade_values_to_rows(
            position, url, table_rows, args.season, week, pulled_at
        )

        issues = validate.validate_trade_values(rows, position=position)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"   [{tag}] {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[position] = "failed: " + "; ".join(
                i.message for i in issues if i.severity == "error"
            )
            print(f"   Not writing output for {position} -- validation failed.")
            continue

        snapshot_path = storage.trade_value_raw_snapshot_path(
            RAW_DIR / "boone_trade_values", "boone", args.season, week, position, pulled_at
        )
        storage.write_raw_snapshot(snapshot_path, table_rows)
        storage.append_trade_values_processed(PROCESSED_PATH, rows)
        run_status[position] = "ok"
        success_count += 1
        print(f"   {len(rows)} rows -> {snapshot_path.relative_to(BASE_DIR)}")

    elapsed = datetime.now() - start
    mins, secs = elapsed.seconds // 60, elapsed.seconds % 60
    print(f"\n{'=' * 45}")
    print(f"Done: {success_count}/{len(wanted_positions)} position(s) written")
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
                "positions": run_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
