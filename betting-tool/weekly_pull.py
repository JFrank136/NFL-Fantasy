#!/usr/bin/env python3
"""
Unattended weekly prop pull: lines -> Draft Sharks projections -> scoring -> immutable snapshot, with checks.

Scheduled (Task Scheduler, see README) for Wednesday morning, with later backup triggers that pass --if-missing, so a
backup only does work when the week still has no snapshot. Each run:
  1. waits for the network (a wake-from-sleep run often starts before DNS is back),
  2. refreshes grades/ for finished games (best effort, never blocks the pull),
  3. pulls the lines and projections and REFUSES to continue if the projections are for a different week than the lines
     (an immutable snapshot with mismatched inputs would poison the out-of-sample test),
  4. scores with the frozen model and saves the snapshot, then confirms a snapshot for that week now exists.
Every outcome is appended to logs/weekly_pull.log; a failure exits non-zero so Task Scheduler's retry fires, and
scorecard.py's health block reports failures and any week left without a snapshot. Games already started when the
pull runs are dropped before scoring (prop_value.py) and never enter the evaluation.

Usage: python weekly_pull.py [--if-missing]
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / 'logs' / 'weekly_pull.log'
HOST = 'api.actionnetwork.com'


def log(status, detail='', log_file=LOG_FILE):
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {status:<8} {detail}\n")
    print(f"{status}: {detail}")


def wait_for_network(tries=12, wait=10, resolve=lambda: socket.getaddrinfo(HOST, 443), sleep=time.sleep):
    for i in range(tries):
        try:
            resolve()
            return True
        except OSError:
            if i < tries - 1:
                sleep(wait)
    return False


def live_weeks(snap_dir):
    """Weeks that already have a live (non-imported) snapshot."""
    weeks = set()
    for mf in Path(snap_dir).glob('*/meta.json'):
        meta = json.loads(mf.read_text())
        if meta.get('provenance') != 'imported':
            weeks.add(int(meta['week']))
    return weeks


def run_script(name):
    """Run one pipeline script with no console window (the task runs under pythonw); on failure log the tail of its output."""
    r = subprocess.run([sys.executable, name], cwd=HERE, env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True, text=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        tail = ' | '.join((r.stderr or r.stdout or '').strip().splitlines()[-3:])
        log('FAILED', f"{name} exit {r.returncode}: {tail[:300]}")
    return r.returncode


def pull(if_missing=False, run=run_script, root=HERE, log_file=LOG_FILE, network=wait_for_network):
    """Returns 0 on success (or a deliberate skip), 1 on failure."""
    root = Path(root)
    snap_dir = root / 'snapshots'
    if not network():
        log('ERROR', 'no network after 2 minutes', log_file)
        return 1
    if run('props_lines.py') != 0:
        log('ERROR', 'props_lines.py failed (slate may not be posted yet)', log_file)
        return 1
    week = int(pd.read_csv(root / 'data' / 'prop_lines.csv')['Week'].min())
    if if_missing and week in live_weeks(snap_dir):
        log('SKIP', f'week {week} already has a snapshot', log_file)
        return 0
    for script in ('grade.py', 'universe.py'):   # history refresh: best effort
        if run(script) != 0:
            log('WARN', f'{script} failed; continuing without refreshed history', log_file)
    if run('ds_projections.py') != 0:
        log('ERROR', 'ds_projections.py failed', log_file)
        return 1
    proj_weeks = set(pd.read_csv(root / 'data' / 'ds_projections.csv')['Week'])
    if proj_weeks != {week}:
        log('ERROR', f'projections are for week(s) {sorted(proj_weeks)} but lines are week {week}; not snapshotting', log_file)
        return 1
    for script in ('prop_value.py', 'snapshot.py'):
        if run(script) != 0:
            log('ERROR', f'{script} failed', log_file)
            return 1
    if week not in live_weeks(snap_dir):
        log('ERROR', f'no snapshot for week {week} after the run', log_file)
        return 1
    log('OK', f'week {week} pulled, scored and snapshotted', log_file)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--if-missing', action='store_true', help='backup run: do nothing if this week already has a snapshot')
    args = ap.parse_args()
    try:
        code = pull(args.if_missing)
    except Exception as e:   # never fail silently
        log('ERROR', f'{type(e).__name__}: {e}')
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()
