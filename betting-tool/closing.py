#!/usr/bin/env python3
"""
Capture the prop lines shortly before kickoff so closing-line value (CLV) can be measured.

Meant to run unattended every ~15 minutes (Task Scheduler, see README). Each run makes one request, keeps only games
kicking off within --within-minutes, and saves closing/<capture time>/prop_lines.csv + meta.json -- unless nothing is
about to start or the lines are identical to the previous capture (duplicate protection). Repeated captures through the
window are fine: scorecard.py uses the latest one made before each game's kickoff.

Reliability: transient network failures are retried; every outcome is appended to closing/closing.log (saved / unchanged /
error with the message), and closing/last_run.json is rewritten each run so a silent scheduler stall is visible
(scorecard.py reports it). Exit code is non-zero only on a real failure.

Usage: python closing.py [--within-minutes 45]
"""
import argparse
import hashlib
import json
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from props_lines import COLUMNS, fetch_markets, parse

HERE = Path(__file__).resolve().parent
CLOSING_DIR = HERE / 'closing'
ATTEMPTS, RETRY_WAIT = 3, 20   # a wake-from-sleep run often starts before DNS is back


def capture(rows, now, within_minutes, closing_dir=CLOSING_DIR):
    """Save rows whose game starts in (now, now + within_minutes]. Returns (dir or None, reason)."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    df['Start'] = pd.to_datetime(df['Start'], utc=True)
    df = df[(df['Start'] > now) & (df['Start'] <= now + timedelta(minutes=within_minutes))]
    if df.empty:
        return None, 'idle'
    csv = df.to_csv(index=False)
    digest = hashlib.sha256(csv.encode()).hexdigest()
    closing_dir.mkdir(exist_ok=True)
    caps = sorted(closing_dir.glob('*/meta.json'))
    if caps and json.loads(caps[-1].read_text()).get('sha256') == digest:
        return None, 'unchanged'
    dest = closing_dir / now.strftime('%Y%m%dT%H%M%SZ')
    dest.mkdir()
    (dest / 'prop_lines.csv').write_text(csv, encoding='utf-8')
    (dest / 'meta.json').write_text(json.dumps({
        'captured_at_utc': now.isoformat(), 'within_minutes': within_minutes, 'quote_rows': len(df),
        'weeks': sorted(int(w) for w in df['Week'].unique()), 'next_kickoff_utc': df['Start'].min().isoformat(),
        'sha256': digest}, indent=2))
    return dest, 'saved'


def record(outcome, detail='', closing_dir=CLOSING_DIR, now=None):
    """Heartbeat for every run; a log line for everything except routine idle runs."""
    closing_dir.mkdir(exist_ok=True)
    now = now or datetime.now(timezone.utc)
    (closing_dir / 'last_run.json').write_text(json.dumps({'at_utc': now.isoformat(), 'outcome': outcome, 'detail': detail}))
    if outcome != 'idle':
        with open(closing_dir / 'closing.log', 'a', encoding='utf-8') as f:
            f.write(f"{now.isoformat(timespec='seconds')}  {outcome:<9} {detail}\n")


def fetch_with_retry(fetch=fetch_markets, attempts=ATTEMPTS, wait=RETRY_WAIT):
    for i in range(1, attempts + 1):
        try:
            return fetch()
        except Exception:
            if i == attempts:
                raise
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--within-minutes', type=float, default=45.0, help='only keep games kicking off within this many minutes')
    args = ap.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        rows = parse(fetch_with_retry())
        dest, reason = capture(rows, now, args.within_minutes)
    except Exception as e:
        record('ERROR', f"{type(e).__name__}: {e}", now=now)
        traceback.print_exc()
        raise SystemExit(1)
    if dest is None:
        record(reason, now=now)
        print(f"Nothing saved ({reason}): no new lines for games starting within {args.within_minutes:g} min.")
    else:
        record('saved', f"{dest.name} ({len(pd.read_csv(dest / 'prop_lines.csv'))} rows)", now=now)
        print(f"Closing-line capture saved -> {dest.relative_to(HERE)}")


if __name__ == '__main__':
    main()
