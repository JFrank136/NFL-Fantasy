#!/usr/bin/env python
"""One-time backfill: pushes the FULL existing rankings_long.csv /
trade_values_long.csv history to Supabase (ignoring push_to_supabase.py's
normal watermark), then sets data/supabase_push_state.json so the regular
push_to_supabase.py doesn't re-push what this just sent.

Run this ONCE: after Task 1 (schema exists), Task 5 (CSVs have
canonical_name), and Task 6 (push_to_supabase.py exists) are all done, and
BEFORE the first scheduled_pull.ps1 run that calls push_to_supabase.py.

IMPORTANT: this assumes the in_season_rankings / in_season_trade_values
tables are EMPTY before this runs (these tables are append-only with no
unique constraint, so re-running this against non-empty tables would create
duplicates). If a prior small verification push left rows in place, clear
them by hand first, e.g.:
    delete from in_season_rankings;
    delete from in_season_trade_values;
(Do NOT touch in_season_pull_status -- that table is a normal upsert table.)

Reuses push_to_supabase.py's own _push_new_rows() helper (chunking,
per-chunk watermark persistence, and error handling) rather than
duplicating that logic -- it's simply called with a zeroed-out state so it
treats every row in the CSVs as "new".

Usage:
    python scripts/backfill_supabase.py
"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.push_to_supabase import (
    BASE_DIR,
    RANKINGS_CSV,
    RANKINGS_FLOAT_COLS,
    RANKINGS_INT_COLS,
    TRADE_FLOAT_COLS,
    TRADE_INT_COLS,
    TRADE_VALUES_CSV,
    _load_env_file,
    _push_new_rows,
)


def _table_row_count(table: str, base_url: str, headers: dict) -> int:
    check_headers = dict(headers)
    check_headers["Prefer"] = "count=exact"
    resp = requests.get(
        f"{base_url}/rest/v1/{table}", headers=check_headers,
        params={"select": "*", "limit": "0"}, timeout=30,
    )
    resp.raise_for_status()
    content_range = resp.headers.get("content-range", "0-0/0")
    return int(content_range.split("/")[-1])


def main() -> int:
    _load_env_file(BASE_DIR / ".env")
    base_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set -- aborting backfill.")
        return 1
    headers = {
        "apikey": service_key, "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    }

    rankings_count = _table_row_count("in_season_rankings", base_url, headers)
    trade_values_count = _table_row_count("in_season_trade_values", base_url, headers)
    if rankings_count or trade_values_count:
        print(
            "Refusing to run: this is a one-time full-history backfill and "
            "the target tables are append-only with no unique constraint, so "
            "re-running it against non-empty tables would create duplicates.\n"
            f"  in_season_rankings currently has {rankings_count} row(s).\n"
            f"  in_season_trade_values currently has {trade_values_count} row(s).\n"
            "If this is intentional (e.g. a prior small verification push left "
            "rows in place), clear them by hand first, e.g.:\n"
            "    delete from in_season_rankings;\n"
            "    delete from in_season_trade_values;\n"
            "(Do NOT touch in_season_pull_status -- that table is a normal "
            "upsert table.)"
        )
        return 1

    # Ignore any existing watermark file -- this is a one-time full-history
    # backfill into tables that must already be empty. _push_new_rows()
    # writes this same dict to data/supabase_push_state.json after every
    # chunk, so it also doubles as our progress/resume state if this script
    # is interrupted and re-run (as long as the tables aren't cleared again
    # in between).
    state = {"rankings_rows_pushed": 0, "trade_values_rows_pushed": 0}

    print("Backfilling full rankings history to in_season_rankings...")
    rankings_ok = _push_new_rows(
        RANKINGS_CSV, "in_season_rankings", RANKINGS_INT_COLS, RANKINGS_FLOAT_COLS,
        state, "rankings_rows_pushed", base_url, headers,
    )
    print(f"  -> {state['rankings_rows_pushed']} rankings row(s) pushed so far.")

    print("Backfilling full trade-values history to in_season_trade_values...")
    trade_ok = _push_new_rows(
        TRADE_VALUES_CSV, "in_season_trade_values", TRADE_INT_COLS, TRADE_FLOAT_COLS,
        state, "trade_values_rows_pushed", base_url, headers,
    )
    print(f"  -> {state['trade_values_rows_pushed']} trade-value row(s) pushed so far.")

    if not (rankings_ok and trade_ok):
        print(
            "Backfill did NOT fully complete -- the watermark in "
            "data/supabase_push_state.json reflects exactly what succeeded. "
            "Fix the underlying issue and re-run this script (or, from this "
            "point on, the regular scripts/push_to_supabase.py) to push the "
            "remainder."
        )
        return 1

    print("Backfill complete -- push state watermark updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
