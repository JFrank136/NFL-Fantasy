"""Refresh the yards-allowed rankings in one go.

Usage: python run_all.py --week 5
Runs cbs.py, last5_yds.py, then process_betting_info.py (output: exports/betting_info.csv).
"""
import argparse
import os
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--week', type=int, help='Week label for the output (default: WEEK in process_betting_info.py)')
args = ap.parse_args()

env = {**os.environ, 'PYTHONUTF8': '1'}
if args.week:
    env['BETTING_WEEK'] = str(args.week)

here = os.path.dirname(os.path.abspath(__file__))
for script in ('cbs.py', 'last5_yds.py', 'process_betting_info.py'):
    print(f"\n>>> {script}")
    if subprocess.run([sys.executable, script], cwd=here, env=env).returncode != 0:
        sys.exit(f"{script} failed; stopping.")
print("\nDone. Open exports/betting_info.csv")
