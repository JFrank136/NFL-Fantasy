"""Refresh the yards-allowed rankings in one go.

Usage: python run_all.py --week 5
Runs cbs.py, last5_yds.py, then process_betting_info.py (output: exports/betting_info.csv),
then props_lines.py -> ds_projections.py -> prop_value.py (output: exports/prop_value.csv),
then snapshot.py (immutable copy under snapshots/). Grade with: python grade.py
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
# Prop-value steps are best-effort: they depend on Action Network having the slate posted.
OPTIONAL = {'props_lines.py', 'ds_projections.py', 'prop_value.py', 'snapshot.py'}
# Best-effort and independent of the pull: grade finished games and refresh the all-lines universe so the
# history (grades/) is current before this week's picks are generated. Failures never block the pull.
for script in ('grade.py', 'universe.py'):
    print(f"\n>>> {script} (history refresh)")
    if subprocess.run([sys.executable, script], cwd=here, env=env).returncode != 0:
        print(f"{script} failed; continuing without refreshed history.")
for script in ('cbs.py', 'last5_yds.py', 'process_betting_info.py', 'props_lines.py', 'ds_projections.py', 'prop_value.py', 'snapshot.py'):
    print(f"\n>>> {script}")
    if subprocess.run([sys.executable, script], cwd=here, env=env).returncode != 0:
        if script in OPTIONAL:
            print(f"{script} failed; skipping the rest of the prop-value steps.")
            break
        sys.exit(f"{script} failed; stopping.")
print("\nDone. Open exports/betting_info.csv")
