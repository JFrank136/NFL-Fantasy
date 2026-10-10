#!/usr/bin/env python3
"""
Compare Draft Sharks stat projections to the best available prop line.

For every player/stat, find the best line a bettor could actually take:
  - Over : the LOWEST line among books whose over odds are >= MIN_ODDS (ties -> better odds)
  - Under: the HIGHEST line among books whose under odds are >= MIN_ODDS
then measure how far the projection sits from it. Output: exports/prop_value.csv
sorted by edge %. Config at the top.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

MIN_ODDS = -130        # ignore juice worse than this (e.g. -145)
MIN_BOOKS = 2          # need at least this many books posting the player/stat
MIN_LINE = {'Pass Yds': 100, 'Rush Yds': 25, 'Rec Yds': 25}  # skip tiny lines (noisy % edges)
STAT_COL = {'Pass Yds': 'pass_yds', 'Rush Yds': 'rush_yds', 'Rec Yds': 'rec_yds'}
TEAM_ALIAS = {'WAS': 'WSH', 'JAC': 'JAX', 'LA': 'LAR', 'ARZ': 'ARI', 'BLT': 'BAL', 'CLV': 'CLE', 'HST': 'HOU'}


def norm_name(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'`-]", '', s)
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_team(t):
    t = str(t).upper()
    return TEAM_ALIAS.get(t, t)


def best_line(df, side):
    ok = df[(df['Side'] == side) & (df['Odds'] >= MIN_ODDS)]
    if ok.empty:
        return None
    # over wants the lowest line, under the highest; then best odds
    ok = ok.sort_values(['Line', 'Odds'], ascending=[side == 'over', False])
    return ok.iloc[0]


def main():
    lines = pd.read_csv('data/prop_lines.csv')
    proj = pd.read_csv('data/ds_projections.csv')
    lines['key'] = lines['Player'].map(norm_name)
    lines['TeamN'] = lines['Team'].map(norm_team)
    proj['key'] = proj['Player'].map(norm_name)
    proj['TeamN'] = proj['Team'].map(norm_team)
    proj = proj.drop_duplicates(['key', 'TeamN'])

    # Projections are means; lines sit near medians and yardage is right-skewed, so a
    # raw projection runs above the line for everyone, more so for low-volume players.
    # Calibrate per stat with a straight-line fit of market line on projection, then
    # measure each bet against the line the market "should" have set for that projection.
    med = lines[lines['Side'] == 'over'].groupby(['key', 'TeamN', 'Stat'])['Line'].median().reset_index()
    med = med.merge(proj, on=['key', 'TeamN'])
    fit = {}
    for stat, col in STAT_COL.items():
        m = med[(med['Stat'] == stat) & (med[col] > 0) & (med['Line'] >= MIN_LINE[stat])]
        slope, icpt = np.polyfit(m[col], m['Line'], 1)
        fit[stat] = (slope, icpt)
        print(f"Calibration {stat}: line = {slope:.2f} x proj + {icpt:.1f}  (n={len(m)})")

    rows = []
    unmatched = set()
    for (key, team, stat), grp in lines.groupby(['key', 'TeamN', 'Stat']):
        p = proj[(proj['key'] == key) & (proj['TeamN'] == team)]
        if p.empty:
            p = proj[proj['key'] == key]  # team mismatch fallback (trades, alias gaps)
        if p.empty:
            unmatched.add(grp['Player'].iloc[0])
            continue
        raw = float(p.iloc[0][STAT_COL[stat]])
        projection = fit[stat][0] * raw + fit[stat][1]  # market-equivalent line for this projection
        n_books = grp['Book'].nunique()
        if n_books < MIN_BOOKS or projection <= 0:
            continue
        cands = []
        for side in ('over', 'under'):
            b = best_line(grp, side)
            if b is None or b['Line'] < MIN_LINE[stat]:
                continue
            edge = projection - b['Line'] if side == 'over' else b['Line'] - projection
            cands.append((edge / b['Line'] * 100, edge, side, b))
        if not cands:
            continue
        pct, edge, side, b = max(cands, key=lambda c: c[0])
        consensus = grp[grp['Side'] == 'over']['Line'].median()
        first = grp.iloc[0]
        rows.append({
            'Player': first['Player'], 'Pos': first['Pos'], 'Team': first['Team'], 'Opp': first['Opp'],
            'Stat': stat, 'Pick': f"{'O' if side == 'over' else 'U'} {b['Line']}",
            'Odds': int(b['Odds']), 'Book': b['Book'], 'DS_Proj': round(raw, 1), 'Fair_Line': round(projection, 1),
            'Edge_Yds': round(edge, 1), 'Edge_Pct': round(pct, 1),
            'Median_Line': consensus, 'Books': n_books, 'Week': int(first['Week']),
        })

    out = pd.DataFrame(rows).sort_values('Edge_Pct', ascending=False)
    import os
    os.makedirs('exports', exist_ok=True)
    out.to_csv('exports/prop_value.csv', index=False)
    print(f"Wrote {len(out)} rows to exports/prop_value.csv (odds >= {MIN_ODDS}, >= {MIN_BOOKS} books)")
    if unmatched:
        print(f"  {len(unmatched)} prop players had no Draft Sharks projection (e.g. {sorted(unmatched)[:5]})")
    print("\nTop edges:")
    print(out.head(12)[['Player', 'Team', 'Stat', 'Pick', 'Odds', 'Book', 'DS_Proj', 'Fair_Line', 'Edge_Yds', 'Edge_Pct']].to_string(index=False))


if __name__ == "__main__":
    main()
