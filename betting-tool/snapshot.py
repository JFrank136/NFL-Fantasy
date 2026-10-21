#!/usr/bin/env python3
"""
Save an immutable, timestamped copy of the inputs and output of a prop-value run.

Each pull overwrites data/prop_lines.csv, data/ds_projections.csv and
exports/prop_value.csv, so without this the quotes a pick was made against are lost
and nothing can be graded honestly later. A snapshot is stamped with the quotes'
capture time (the mtime of prop_lines.csv, i.e. when they were pulled), which is
what grade.py compares against kickoff to rule out post-kickoff quotes.

Usage: python snapshot.py    (run_all.py calls this last; re-running on unchanged files is a no-op)
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
FILES = ['data/prop_lines.csv', 'data/ds_projections.csv', 'exports/prop_value.csv']


def _digest(root):
    h = hashlib.sha256()
    for f in FILES:
        h.update((root / f).read_bytes())
    return h.hexdigest()


def take(root=HERE, snap_dir=SNAP_DIR):
    """Copy the three files into snapshots/<captured_at>/. Returns the dir, or None if unchanged."""
    root, snap_dir = Path(root), Path(snap_dir)
    missing = [f for f in FILES if not (root / f).exists()]
    if missing:
        raise SystemExit(f"Cannot snapshot, missing: {', '.join(missing)}")
    digest = _digest(root)
    snap_dir.mkdir(exist_ok=True)
    for d in snap_dir.iterdir():
        meta = d / 'meta.json'
        if meta.exists() and json.loads(meta.read_text())['sha256'] == digest:
            return None
    captured = datetime.fromtimestamp((root / FILES[0]).stat().st_mtime, tz=timezone.utc)
    dest = snap_dir / captured.strftime('%Y%m%dT%H%M%SZ')
    dest.mkdir()
    for f in FILES:
        shutil.copy2(root / f, dest / Path(f).name)
    lines = pd.read_csv(dest / 'prop_lines.csv')
    meta = {'captured_at_utc': captured.isoformat(), 'taken_at_utc': datetime.now(timezone.utc).isoformat(),
            'week': int(lines['Week'].iloc[0]), 'quote_rows': len(lines),
            'pick_rows': len(pd.read_csv(dest / 'prop_value.csv')), 'sha256': digest}
    (dest / 'meta.json').write_text(json.dumps(meta, indent=2))
    return dest


def import_picks(path, season, snap_dir=SNAP_DIR):
    """Save a historical prop_value.csv that has no matching quotes file (e.g. a past week's export).

    Marked provenance='imported': its capture time is unknown, so grade.py takes kickoff times from the
    nflverse schedule and ASSUMES the picks were made pregame. Treat results as less trustworthy than
    live snapshots.
    """
    path, snap_dir = Path(path), Path(snap_dir)
    picks = pd.read_csv(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    snap_dir.mkdir(exist_ok=True)
    for d in snap_dir.iterdir():
        meta = d / 'meta.json'
        if meta.exists() and json.loads(meta.read_text())['sha256'] == digest:
            return None
    week = int(picks['Week'].iloc[0])
    dest = snap_dir / f'import_{season}_w{week}'
    dest.mkdir()
    shutil.copy2(path, dest / 'prop_value.csv')
    meta = {'provenance': 'imported', 'season': season, 'week': week, 'captured_at_utc': None,
            'taken_at_utc': datetime.now(timezone.utc).isoformat(), 'pick_rows': len(picks), 'sha256': digest}
    (dest / 'meta.json').write_text(json.dumps(meta, indent=2))
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--import-picks', metavar='CSV', help='import a past prop_value.csv with no quotes file')
    ap.add_argument('--season', type=int, default=2026, help='season for --import-picks')
    args = ap.parse_args()
    dest = import_picks(args.import_picks, args.season) if args.import_picks else take()
    print("Snapshot unchanged since last one; skipped." if dest is None else f"Snapshot saved -> {dest.relative_to(HERE)}")


if __name__ == '__main__':
    main()
