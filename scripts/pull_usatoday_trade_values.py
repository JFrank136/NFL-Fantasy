#!/usr/bin/env python
"""Pulls USA Today's trade value chart (QB/RB/WR/TE) for the current week and
writes it to data/raw/usatoday_trade_values/ (immutable snapshot) and
 data/processed/trade_values_long.csv (append) -- the same shared table every
trade-value source appends to, distinguished by source="usatoday".

USA Today publishes one combined article per week, so either article discovery
succeeds for the requested week or all requested positions are treated as not
yet published. Exits non-zero on discovery/fetch/parsing failures or validation
errors. Writes data/last_usatoday_trade_values_status.json in the same
{run_at, ok, positions} shape consumed by scheduled_pull.ps1/status email logic.

Usage:
    python scripts/pull_usatoday_trade_values.py
    python scripts/pull_usatoday_trade_values.py --week 2
    python scripts/pull_usatoday_trade_values.py --position rb,wr
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
from src.sources.usatoday_trade_values import (
    POSITIONS,
    UsaTodayTradeValueFetchError,
    discover_article_url,
    fetch_trade_chart,
)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "trade_values_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_usatoday_trade_values_status.json"


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

    invalid_positions = [p for p in wanted_positions if p not in POSITIONS]
    if invalid_positions:
        parser.error(
            f"Unknown position(s): {', '.join(invalid_positions)}; "
            f"expected qb, rb, wr, te, or all."
        )

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(f"Starting USA Today trade-value pull -- week {week}, positions {wanted_positions}")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    try:
        url = discover_article_url(week, season=args.season)
    except UsaTodayTradeValueFetchError as e:
        print(f"\n[FAILED] Could not discover this week's article URL: {e}")
        _write_status({p: f"failed: could not discover article URL: {e}" for p in wanted_positions})
        sys.exit(1)

    if url is None:
        print("   Not yet published for this week -- skipping.")
        _write_status({p: "not_yet_published" for p in wanted_positions}, any_errors=False)
        return

    print(f"   Found article: {url}\n")

    try:
        chart = fetch_trade_chart(url, positions=wanted_positions)
    except UsaTodayTradeValueFetchError as e:
        print(f"\n[FAILED] Could not fetch/parse the trade chart: {e}")
        _write_status({p: f"failed: {e}" for p in wanted_positions})
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAILED] Unexpected failure fetching the trade chart: {e}")
        traceback.print_exc()
        _write_status({p: f"failed: unexpected error: {e}" for p in wanted_positions})
        sys.exit(1)

    run_status = {}
    any_errors = False
    success_count = 0

    for i, position in enumerate(wanted_positions, 1):
        print(f"[{i}/{len(wanted_positions)}] {position}...")
        table_rows = chart.get(position, [])

        # Normalize before validating -- validate_trade_values expects TradeValueRow objects.
        # This order must stay fixed: normalize -> validate -> write raw snapshot + CSV.
        rows = normalize.usatoday_trade_values_to_rows(
            position, url, table_rows, args.season, week, pulled_at
        )

        issues = validate.validate_trade_values(rows, position=position)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"   [{tag}] {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[position] = "failed: " + "; ".join(
                issue.message for issue in issues if issue.severity == "error"
            )
            print(f"   Not writing output for {position} -- validation failed.")
            continue

        snapshot_path = storage.trade_value_raw_snapshot_path(
            RAW_DIR / "usatoday_trade_values", "usatoday", args.season, week, position, pulled_at
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