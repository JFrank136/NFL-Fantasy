#!/usr/bin/env python3
"""
Capture the prop lines shortly before kickoff so closing-line value (CLV) can be measured later.

The weekly pull is hours or days before the games, and lines move. Run this close to kickoff (see README for a
schedule); it saves closing/<capture time>/prop_lines.csv with only games starting within --within-hours, plus a
meta.json, and skips a capture identical to the previous one. Nothing here changes picks or snapshots; scorecard.py
reads these files and, for each pick, uses the latest capture made before that game's kickoff.

Usage: python closing.py [--within-hours 6]
"""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from props_lines import COLUMNS, fetch_markets, parse

HERE = Path(__file__).resolve().parent
CLOSING_DIR = HERE / 'closing'


def capture(rows, now, within_hours, closing_dir=CLOSING_DIR):
    """Save rows whose game starts in (now, now + within_hours]. Returns the new dir, or None if nothing to save."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    df['Start'] = pd.to_datetime(df['Start'], utc=True)
    df = df[(df['Start'] > now) & (df['Start'] <= now + timedelta(hours=within_hours))]
    if df.empty:
        return None
    csv = df.to_csv(index=False)
    digest = hashlib.sha256(csv.encode()).hexdigest()
    closing_dir.mkdir(exist_ok=True)
    caps = sorted(closing_dir.glob('*/meta.json'))
    if caps and json.loads(caps[-1].read_text()).get('sha256') == digest:
        return None
    dest = closing_dir / now.strftime('%Y%m%dT%H%M%SZ')
    dest.mkdir()
    (dest / 'prop_lines.csv').write_text(csv, encoding='utf-8')
    (dest / 'meta.json').write_text(json.dumps({
        'captured_at_utc': now.isoformat(), 'within_hours': within_hours, 'quote_rows': len(df),
        'weeks': sorted(int(w) for w in df['Week'].unique()), 'next_kickoff_utc': df['Start'].min().isoformat(),
        'sha256': digest}, indent=2))
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--within-hours', type=float, default=6.0, help='only keep games kicking off within this many hours')
    args = ap.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = parse(fetch_markets())
    dest = capture(rows, now, args.within_hours)
    print(f"No games in the next {args.within_hours:g}h, or lines unchanged since the last capture; nothing saved."
          if dest is None else f"Closing-line capture saved -> {dest.relative_to(HERE)}")


if __name__ == '__main__':
    main()
