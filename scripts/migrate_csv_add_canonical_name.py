#!/usr/bin/env python
"""One-time migration: adds a canonical_name column to the existing
processed CSVs, which were written before RankingRow/TradeValueRow gained
that field. Run this once, right after Task 4 lands and before the next
pipeline run -- otherwise the next append writes rows with one more column
than the existing header declares.

Usage:
    python scripts/migrate_csv_add_canonical_name.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.player_identity import canonical_name_for
from src.schema import LONG_FORMAT_COLUMNS, TRADE_VALUE_COLUMNS

BASE_DIR = Path(__file__).resolve().parent.parent
RANKINGS_CSV = BASE_DIR / "data" / "processed" / "rankings_long.csv"
TRADE_VALUES_CSV = BASE_DIR / "data" / "processed" / "trade_values_long.csv"


def migrate(path: Path, columns: list[str]) -> None:
    if not path.exists():
        print(f"{path} does not exist -- nothing to migrate.")
        return
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "canonical_name" in reader.fieldnames:
            print(f"{path} already has canonical_name -- skipping.")
            return
        rows = list(reader)

    for row in rows:
        row["canonical_name"] = canonical_name_for(row["player_name"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Migrated {len(rows)} row(s) in {path}.")


if __name__ == "__main__":
    migrate(RANKINGS_CSV, LONG_FORMAT_COLUMNS)
    migrate(TRADE_VALUES_CSV, TRADE_VALUE_COLUMNS)
