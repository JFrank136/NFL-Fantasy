#!/usr/bin/env python3
"""
Grade EVERY posted line in the saved snapshots, not just the picks.

grade.py only sees the ~135-260 picks a week, which are selected by the model being tested. This builds
the unselected universe -- each sportsbook line for every player/stat, from the latest pre-kickoff snapshot,
joined to the Draft Sharks projection and the nflverse actual -- so calibration and "does the projection add
anything beyond the market?" are measured on all of it. Output: grades/universe.csv (one row per
week/player/stat/book/line). Re-running is idempotent and picks up new snapshots/results as they land.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from grade import ACTUAL_COL, SNAP_DIR, load_actuals, season_of
from prop_value import STAT_COL, norm_name, norm_team

HERE = Path(__file__).resolve().parent
OUT_FILE = HERE / 'grades' / 'universe.csv'


def load_lines(snap_dir=SNAP_DIR):
    """Latest pre-kickoff quote per week/player/stat/book/line/side, with its projection attached."""
    frames = []
    for meta_file in sorted(Path(snap_dir).glob('*/meta.json')):
        meta = json.loads(meta_file.read_text())
        d = meta_file.parent
        if meta.get('provenance') == 'imported' or not (d / 'prop_lines.csv').exists():
            continue  # imported weeks carry picks only, no quotes
        lines = pd.read_csv(d / 'prop_lines.csv')
        proj = pd.read_csv(d / 'ds_projections.csv')
        for df in (lines, proj):
            df['key'] = df['Player'].map(norm_name)
            df['TeamN'] = df['Team'].map(norm_team)
        proj = proj.drop_duplicates(['key', 'TeamN']).drop(columns=['Week', 'Player', 'Pos', 'Team', 'Opp'], errors='ignore')
        lines['Start'] = pd.to_datetime(lines['Start'], utc=True)
        lines['captured_at'] = pd.to_datetime(meta['captured_at_utc'], utc=True)
        lines = lines[lines['captured_at'] < lines['Start']].merge(proj, on=['key', 'TeamN'], how='left')
        frames.append(lines)
    if not frames:
        raise SystemExit("No live snapshots with quotes found; run snapshot.py first.")
    allq = pd.concat(frames, ignore_index=True)
    allq['proj'] = [r[STAT_COL[r['Stat']]] for r in allq.to_dict('records')]
    k = ['Week', 'key', 'TeamN', 'Stat']
    allq = allq[allq['captured_at'] == allq.groupby(k)['captured_at'].transform('max')]
    return allq.drop_duplicates(k + ['Book', 'Side', 'Line'])


def build(snap_dir=SNAP_DIR):
    q = load_lines(snap_dir)
    stats, snaps = load_actuals({season_of(s) for s in q['Start']})
    idx = {(r.week, r.key, r.TeamN): r for r in stats.itertuples()}
    played = {(r.week, r.key, r.TeamN): r.snaps > 0 for r in snaps.itertuples()}

    def actual(r):
        s = idx.get((r['Week'], r['key'], r['TeamN']))
        if s is not None:
            return float(getattr(s, ACTUAL_COL[r['Stat']]))
        return 0.0 if played.get((r['Week'], r['key'], r['TeamN'])) else np.nan  # absent entirely -> unknown/DNP

    q['Actual'] = [actual(r) for r in q.to_dict('records')]
    k = ['Week', 'key', 'TeamN', 'Stat']
    q['Median_Line'] = q[q['Side'] == 'over'].groupby(k)['Line'].transform('median').reindex(q.index)
    q['Median_Line'] = q.groupby(k)['Median_Line'].transform('max')
    q['Books'] = q.groupby(k)['Book'].transform('nunique')
    cols = ['Week', 'Player', 'Pos', 'Team', 'Opp', 'Stat', 'Book', 'Side', 'Line', 'Odds', 'key', 'TeamN',
            'Median_Line', 'Books', 'proj', 'Actual', 'captured_at', 'Start']
    return q[cols]


def main():
    u = build()
    OUT_FILE.parent.mkdir(exist_ok=True)
    u.drop(columns=['key', 'TeamN']).to_csv(OUT_FILE, index=False)
    ps = u.drop_duplicates(['Week', 'key', 'TeamN', 'Stat'])
    print(f"{len(u)} line quotes / {len(ps)} player-stats over weeks {sorted(u['Week'].unique())}; "
          f"{ps['Actual'].notna().sum()} have actuals, {ps['proj'].notna().sum()} have projections -> {OUT_FILE.name}")


if __name__ == '__main__':
    main()
