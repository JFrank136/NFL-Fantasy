#!/usr/bin/env python
"""Pushes newly-pulled rows from the local processed CSVs into Supabase, and
upserts the latest pull-status snapshot. Called by scheduled_pull.ps1 after
each pull; also safe to run by hand.

Only pushes rows appended since the last successful push (tracked by row
count in data/supabase_push_state.json) -- the CSVs are append-only, so a
simple "rows pushed so far" watermark avoids re-inserting already-pushed
history every run. A push failure here does NOT mean data was lost: the
local CSV already has it, and the watermark stays put so the same unpushed
rows get retried next run.

Usage:
    python scripts/push_to_supabase.py
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, either in the
environment or in in-season/.env (see .env.example) -- this script loads
.env itself so scheduled_pull.ps1 doesn't need to export anything.
"""
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
RANKINGS_CSV = BASE_DIR / "data" / "processed" / "rankings_long.csv"
TRADE_VALUES_CSV = BASE_DIR / "data" / "processed" / "trade_values_long.csv"
ROS_RANKINGS_CSV = BASE_DIR / "data" / "processed" / "ros_rankings_long.csv"
RUN_STATUS_PATH = BASE_DIR / "data" / "last_run_status.json"
TRADE_STATUS_PATH = BASE_DIR / "data" / "last_trade_values_status.json"
ROS_STATUS_PATH = BASE_DIR / "data" / "last_draftsharks_ros_status.json"
PUSH_STATE_PATH = BASE_DIR / "data" / "supabase_push_state.json"

RANKINGS_INT_COLS = {"season", "week", "rank", "tier", "bye"}
RANKINGS_FLOAT_COLS = {"projection", "floor_proj", "ceiling_proj"}
TRADE_INT_COLS = {"season", "week", "rank"}
TRADE_FLOAT_COLS = {"value_col1", "value_col2"}
ROS_RANKINGS_INT_COLS = {
    "season", "as_of_week", "rank", "tier_overall", "tier_positional",
    "games_played", "bye",
}
ROS_RANKINGS_FLOAT_COLS = {"projection", "floor_proj", "ceiling_proj", "ds_value"}

CHUNK = 500


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def _coerce_row(row: dict, int_cols: set, float_cols: set) -> dict:
    out = dict(row)
    for col in int_cols:
        out[col] = int(out[col]) if out.get(col) not in (None, "") else None
    for col in float_cols:
        out[col] = float(out[col]) if out.get(col) not in (None, "") else None
    return out


def _read_state() -> dict:
    if PUSH_STATE_PATH.exists():
        return json.loads(PUSH_STATE_PATH.read_text(encoding="utf-8"))
    return {
        "rankings_rows_pushed": 0, "trade_values_rows_pushed": 0,
        "ros_rankings_rows_pushed": 0,
    }


def _write_state(state: dict) -> None:
    PUSH_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _read_new_rows(csv_path: Path, already_pushed: int) -> list:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[already_pushed:]


def _insert(table: str, rows: list, base_url: str, headers: dict) -> None:
    if not rows:
        return
    resp = requests.post(f"{base_url}/rest/v1/{table}", headers=headers, json=rows, timeout=30)
    resp.raise_for_status()


def _get_current_status(dataset: str, base_url: str, headers: dict):
    resp = requests.get(
        f"{base_url}/rest/v1/in_season_pull_status",
        headers=headers, params={"dataset": f"eq.{dataset}", "select": "*"}, timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def _upsert_status(dataset: str, payload: dict, base_url: str, headers: dict) -> None:
    upsert_headers = dict(headers)
    upsert_headers["Prefer"] = "resolution=merge-duplicates"
    resp = requests.post(
        f"{base_url}/rest/v1/in_season_pull_status", headers=upsert_headers,
        json=[{"dataset": dataset, **payload}], timeout=30,
    )
    resp.raise_for_status()


def _push_new_rows(
    csv_path: Path, table: str, int_cols: set, float_cols: set,
    state: dict, state_key: str, base_url: str, headers: dict,
) -> bool:
    """Pushes unpushed rows from csv_path to table in chunks, writing the
    watermark to disk after each successful chunk. Returns True if this
    dataset's push fully succeeded (or had nothing to do), False on any
    failure (state reflects whatever chunk(s) DID succeed before the
    failure)."""
    already_pushed = state[state_key]

    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            total_rows = sum(1 for _ in csv.DictReader(f))
        if total_rows < already_pushed:
            print(
                f"WARNING: {csv_path} has fewer rows ({total_rows}) than the "
                f"push watermark ({already_pushed}) -- was it manually edited "
                "or regenerated? Not pushing anything for this file until "
                "this is resolved by hand."
            )
            return False

    raw_rows = _read_new_rows(csv_path, already_pushed)
    if not raw_rows:
        print(f"No new rows to push for {table}.")
        return True

    pushed = 0
    try:
        for i in range(0, len(raw_rows), CHUNK):
            chunk = [
                _coerce_row(r, int_cols, float_cols) for r in raw_rows[i:i + CHUNK]
            ]
            _insert(table, chunk, base_url, headers)
            pushed += len(chunk)
            state[state_key] = already_pushed + pushed
            _write_state(state)
        print(f"Pushed {pushed} new row(s) to {table}.")
        return True
    except requests.RequestException as e:
        print(
            f"WARNING: push to {table} failed after {pushed}/{len(raw_rows)} "
            f"new row(s) this run (watermark saved through the successful "
            f"part, will retry the rest next run): {e}"
        )
        return False
    except (ValueError, KeyError) as e:
        print(
            f"WARNING: failed to process rows for {table} after {pushed}/"
            f"{len(raw_rows)} new row(s) pushed this run: {e}"
        )
        return False


def main() -> int:
    _load_env_file(BASE_DIR / ".env")
    base_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set -- skipping Supabase push.")
        return 1

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    state = _read_state()
    state.setdefault("ros_rankings_rows_pushed", 0)
    any_failure = False

    if not _push_new_rows(
        RANKINGS_CSV, "in_season_rankings", RANKINGS_INT_COLS, RANKINGS_FLOAT_COLS,
        state, "rankings_rows_pushed", base_url, headers,
    ):
        any_failure = True

    if not _push_new_rows(
        TRADE_VALUES_CSV, "in_season_trade_values", TRADE_INT_COLS, TRADE_FLOAT_COLS,
        state, "trade_values_rows_pushed", base_url, headers,
    ):
        any_failure = True

    if not _push_new_rows(
        ROS_RANKINGS_CSV, "in_season_ros_rankings", ROS_RANKINGS_INT_COLS, ROS_RANKINGS_FLOAT_COLS,
        state, "ros_rankings_rows_pushed", base_url, headers,
    ):
        any_failure = True

    for status_path, dataset_prefix, key_field in (
        (RUN_STATUS_PATH, "rankings", "combos"),
        (TRADE_STATUS_PATH, "trade_values", "positions"),
        (ROS_STATUS_PATH, "ros_rankings", "combos"),
    ):
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        for key, value in status.get(key_field, {}).items():
            dataset = f"{dataset_prefix}/{key}"
            ok = value == "ok"
            try:
                if ok:
                    last_success_at = status["run_at"]
                else:
                    current = _get_current_status(dataset, base_url, headers)
                    last_success_at = (current or {}).get("last_success_at")
                _upsert_status(dataset, {
                    "last_attempt_at": status["run_at"],
                    "last_success_at": last_success_at,
                    "status": "healthy" if ok else "failed",
                    "message": None if ok else str(value),
                    "row_count": None,
                }, base_url, headers)
            except requests.RequestException as e:
                print(f"WARNING: status upsert failed for {dataset}: {e}")
                any_failure = True

    return 1 if any_failure else 0


if __name__ == "__main__":
    sys.exit(main())
