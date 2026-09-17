"""Writes pull output to local files. Append-only by construction: raw
snapshots are one immutable file per pull (timestamp in the filename), and the
processed CSV is opened in append mode and never rewritten -- re-pulling a
week just adds rows with a newer `pulled_at`, preserving every prior pull.
"""

import csv
import json
from dataclasses import asdict
from pathlib import Path

from src.schema import (
    LONG_FORMAT_COLUMNS, RankingRow, ROS_RANKING_COLUMNS, RosRankingRow,
    TRADE_VALUE_COLUMNS, TradeValueRow,
)


def raw_snapshot_path(
    raw_dir: Path, source: str, season: int, week: int, scoring: str, pulled_at: str
) -> Path:
    # pulled_at is an ISO timestamp (has colons) -- not filename-safe as-is.
    safe_ts = pulled_at.replace(":", "").replace("-", "")
    return raw_dir / source / str(season) / f"week{week:02d}_{scoring}_{safe_ts}.json"


def write_raw_snapshot(path: Path, raw_rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(r) for r in raw_rows]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_processed(processed_path: Path, rows: list[RankingRow]) -> None:
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not processed_path.exists()
    with processed_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LONG_FORMAT_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def trade_value_raw_snapshot_path(
    raw_dir: Path, source: str, season: int, week: int, position: str, pulled_at: str
) -> Path:
    safe_ts = pulled_at.replace(":", "").replace("-", "")
    return raw_dir / source / str(season) / f"week{week:02d}_{position}_{safe_ts}.json"


def append_trade_values_processed(processed_path: Path, rows: list[TradeValueRow]) -> None:
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not processed_path.exists()
    with processed_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_VALUE_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def ros_raw_snapshot_path(
    raw_dir: Path, source: str, season: int, as_of_week: int, scoring: str, pulled_at: str
) -> Path:
    safe_ts = pulled_at.replace(":", "").replace("-", "")
    return raw_dir / source / str(season) / f"asofweek{as_of_week:02d}_{scoring}_{safe_ts}.json"


def append_ros_rankings_processed(processed_path: Path, rows: list[RosRankingRow]) -> None:
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not processed_path.exists()
    with processed_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ROS_RANKING_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
