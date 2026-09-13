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
RUN_STATUS_PATH = BASE_DIR / "data" / "last_run_status.json"
TRADE_STATUS_PATH = BASE_DIR / "data" / "last_trade_values_status.json"
PUSH_STATE_PATH = BASE_DIR / "data" / "supabase_push_state.json"

RANKINGS_INT_COLS = {"season", "week", "rank", "tier", "bye"}
RANKINGS_FLOAT_COLS = {"projection", "floor_proj", "ceiling_proj"}
TRADE_INT_COLS = {"season", "week", "rank"}
TRADE_FLOAT_COLS = {"value_col1", "value_col2"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


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
    return {"rankings_rows_pushed": 0, "trade_values_rows_pushed": 0}


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

    new_rankings = [
        _coerce_row(r, RANKINGS_INT_COLS, RANKINGS_FLOAT_COLS)
        for r in _read_new_rows(RANKINGS_CSV, state["rankings_rows_pushed"])
    ]
    try:
        _insert("in_season_rankings", new_rankings, base_url, headers)
        state["rankings_rows_pushed"] += len(new_rankings)
        print(f"Pushed {len(new_rankings)} new rankings row(s).")
    except requests.RequestException as e:
        print(f"WARNING: rankings push failed, will retry next run: {e}")

    new_trade_values = [
        _coerce_row(r, TRADE_INT_COLS, TRADE_FLOAT_COLS)
        for r in _read_new_rows(TRADE_VALUES_CSV, state["trade_values_rows_pushed"])
    ]
    try:
        _insert("in_season_trade_values", new_trade_values, base_url, headers)
        state["trade_values_rows_pushed"] += len(new_trade_values)
        print(f"Pushed {len(new_trade_values)} new trade-value row(s).")
    except requests.RequestException as e:
        print(f"WARNING: trade-value push failed, will retry next run: {e}")

    _write_state(state)

    for status_path, dataset_prefix, key_field in (
        (RUN_STATUS_PATH, "rankings", "combos"),
        (TRADE_STATUS_PATH, "trade_values", "positions"),
    ):
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        for key, value in status.get(key_field, {}).items():
            dataset = f"{dataset_prefix}/{key}"
            ok = value == "ok"
            try:
                current = _get_current_status(dataset, base_url, headers)
                last_success_at = status["run_at"] if ok else (current or {}).get("last_success_at")
                _upsert_status(dataset, {
                    "last_attempt_at": status["run_at"],
                    "last_success_at": last_success_at,
                    "status": "healthy" if ok else "failed",
                    "message": None if ok else str(value),
                    "row_count": None,
                }, base_url, headers)
            except requests.RequestException as e:
                print(f"WARNING: status upsert failed for {dataset}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
