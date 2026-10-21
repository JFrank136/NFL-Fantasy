#!/usr/bin/env python3
"""
Grade saved prop-value picks against nflverse actuals and report hit rate / units / residuals.

Reads every snapshot under snapshots/ (see snapshot.py). For each week/player/stat the pick
from the latest snapshot captured BEFORE kickoff is graded at its listed line and odds:
  win / loss / push  - player has an nflverse game row
  pending            - game started less than PENDING_HOURS ago
  void               - game is over, the team has snap counts, and the player has none (did not play)
  unverified         - game is over but no stats row AND no snap-count evidence either way (name
                       mismatch or data lag). Never treated as 0 or a loss, excluded from the record.
A player with snaps but no stats row played and recorded 0 (Basis=snap_count_zero) and is graded on 0.
  late_quote         - every snapshot for it was captured at/after kickoff (excluded)
Units are flat 1-unit stakes at the listed odds and are HYPOTHETICAL unless you actually bet.
Each row is one player/stat opportunity, not one per sportsbook.

Usage: python grade.py   -> grades/graded_picks.csv, grades/report.csv, console summary
"""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from prop_value import norm_name, norm_team

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
OUT_DIR = HERE / 'grades'
PENDING_HOURS = 5
ACTUAL_COL = {'Pass Yds': 'passing_yards', 'Rush Yds': 'rushing_yards', 'Rec Yds': 'receiving_yards', 'Receptions': 'receptions'}


def settle(direction, line, actual):
    """win/loss/push for an over ('O') or under ('U') against the stat actual."""
    if actual == line:
        return 'push'
    return 'win' if (actual > line) == (direction == 'O') else 'loss'


def profit_units(result, odds):
    """Net units on a 1-unit stake at American odds. Push/void/other -> 0."""
    if result == 'win':
        return odds / 100 if odds > 0 else 100 / -odds
    return -1.0 if result == 'loss' else 0.0


def break_even(odds):
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def wilson(wins, n, z=1.96):
    """95% Wilson interval for a hit rate; (nan, nan) when n == 0."""
    if n == 0:
        return float('nan'), float('nan')
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def season_of(start):
    return start.year if start.month >= 8 else start.year - 1


_SCHEDULES = {}


def kickoff(season, week, team):
    """Kickoff (UTC) of a team's game that week from the nflverse schedule; NaT if not found."""
    if season not in _SCHEDULES:
        import nflreadpy
        sc = nflreadpy.load_schedules([season]).to_pandas()
        sc['ko'] = pd.to_datetime(sc['gameday'] + ' ' + sc['gametime']).dt.tz_localize(
            'America/New_York', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
        _SCHEDULES[season] = sc
    sc = _SCHEDULES[season]
    t = norm_team(team)
    hit = sc[(sc['week'] == week) & ((sc['home_team'].map(norm_team) == t) | (sc['away_team'].map(norm_team) == t))]
    return hit['ko'].iloc[0] if len(hit) else pd.NaT


def load_picks(snap_dir=SNAP_DIR):
    """One row per week/player/stat from the latest pre-kickoff snapshot, plus late-quote rows."""
    frames = []
    for meta_file in sorted(Path(snap_dir).glob('*/meta.json')):
        d = meta_file.parent
        meta = json.loads(meta_file.read_text())
        picks = pd.read_csv(d / 'prop_value.csv')
        if meta.get('provenance') == 'imported':
            picks['Start'] = picks.apply(lambda r: kickoff(meta['season'], r['Week'], r['Team']), axis=1)
            picks['captured_at'] = picks['Start'] - pd.Timedelta(seconds=1)  # assumed pregame
        else:
            lines = pd.read_csv(d / 'prop_lines.csv')
            start = lines.groupby(['Player', 'Team', 'Stat'])['Start'].min().rename('Start').reset_index()
            picks = picks.merge(start, on=['Player', 'Team', 'Stat'], how='left')
            picks['Start'] = pd.to_datetime(picks['Start'], utc=True)
            picks['captured_at'] = pd.to_datetime(meta['captured_at_utc'], utc=True)
        picks['Provenance'] = meta.get('provenance', 'live')
        picks['snapshot'] = d.name
        frames.append(picks)
    if not frames:
        raise SystemExit("No snapshots found; run snapshot.py first.")
    allp = pd.concat(frames, ignore_index=True)
    allp['pregame'] = allp['captured_at'] < allp['Start']
    key = ['Week', 'Player', 'Stat']
    pre = allp[allp['pregame']].sort_values('captured_at').drop_duplicates(key, keep='last')
    late = allp[~allp['pregame']].drop_duplicates(key, keep='last')
    late = late[~late.set_index(key).index.isin(pre.set_index(key).index)].assign(Result='late_quote')
    return pre, late


def load_actuals(seasons):
    import nflreadpy
    df = nflreadpy.load_player_stats(sorted(seasons)).to_pandas()
    df = df[df['season_type'] == 'REG'].copy()
    df['key'] = df['player_display_name'].map(norm_name)
    df['TeamN'] = df['team'].map(norm_team)
    sn = nflreadpy.load_snap_counts(sorted(seasons)).to_pandas()
    sn['key'] = sn['player'].map(norm_name)
    sn['TeamN'] = sn['team'].map(norm_team)
    sn['snaps'] = sn[['offense_snaps', 'defense_snaps', 'st_snaps']].fillna(0).sum(axis=1)
    return df, sn


def resolve(row, col, direction, line, played, team_has_snaps, start, now):
    """(actual, result, basis) for one pick. `row` is the nflverse stats row or None; `played` is
    True/False if the player is in the snap counts (None if absent); `team_has_snaps` says the
    team's snap counts for that week are published."""
    if row is not None:
        actual = float(getattr(row, col))
        return actual, settle(direction, line, actual), 'nflverse_stats'
    if now < start + timedelta(hours=PENDING_HOURS):
        return None, 'pending', None
    if played:
        return 0.0, settle(direction, line, 0.0), 'snap_count_zero'
    if team_has_snaps:
        return None, 'void', 'snap_count_dnp'
    return None, 'unverified', None


def grade(pre, actuals, snaps=None, now=None):
    now = now or datetime.now(timezone.utc)
    idx = {(r.season, r.week, r.key, r.TeamN): r for r in actuals.itertuples()}
    played = {}
    team_has_snaps = set()
    if snaps is not None:
        for r in snaps.itertuples():
            played[(r.season, r.week, r.key, r.TeamN)] = r.snaps > 0
            team_has_snaps.add((r.season, r.week, r.TeamN))
    out = []
    for r in pre.to_dict('records'):
        season = season_of(r['Start'])
        direction, line = r['Pick'].split(' ')[0], float(r['Pick'].split(' ')[1])
        row = idx.get((season, r['Week'], norm_name(r['Player']), norm_team(r['Team'])))
        actual, result, basis = resolve(row, ACTUAL_COL[r['Stat']], direction, line,
                                        played.get((season, r['Week'], norm_name(r['Player']), norm_team(r['Team']))),
                                        (season, r['Week'], norm_team(r['Team'])) in team_has_snaps,
                                        r['Start'], now)
        out.append({**r, 'Direction': direction, 'Line': line, 'Actual': actual, 'Result': result, 'Basis': basis,
                    'Units': profit_units(result, r['Odds']),
                    'Resid_DS': None if actual is None else actual - r['DS_Proj'],
                    'Resid_Fair': None if actual is None else actual - r['Fair_Line']})
    return pd.DataFrame(out)


def summarize(g, by):
    s = g[g['Result'].isin(['win', 'loss', 'push'])]
    rows = []
    for k, grp in s.groupby(by):
        w, l, p = (grp['Result'] == x for x in ('win', 'loss', 'push'))
        n = int(w.sum() + l.sum())
        lo, hi = wilson(int(w.sum()), n)
        rows.append({**dict(zip(by, k if isinstance(k, tuple) else (k,))), 'N': len(grp), 'W': int(w.sum()),
                     'L': int(l.sum()), 'P': int(p.sum()), 'Hit%': round(100 * w.sum() / n, 1) if n else None,
                     'CI95_lo': round(100 * lo, 1), 'CI95_hi': round(100 * hi, 1),
                     'BreakEven%': round(100 * grp['Odds'].map(break_even).mean(), 1),
                     'Units': round(grp['Units'].sum(), 2), 'ROI%': round(100 * grp['Units'].sum() / len(grp), 1),
                     'Bias_DS': round(grp['Resid_DS'].mean(), 1), 'MAE_DS': round(grp['Resid_DS'].abs().mean(), 1),
                     'MAE_Fair': round(grp['Resid_Fair'].abs().mean(), 1)})
    return pd.DataFrame(rows)


def main():
    pre, late = load_picks()
    seasons = {season_of(s) for s in pre['Start']}
    stats, snaps = load_actuals(seasons)
    g = grade(pre, stats, snaps)
    g = pd.concat([g, late], ignore_index=True)
    OUT_DIR.mkdir(exist_ok=True)
    g.to_csv(OUT_DIR / 'graded_picks.csv', index=False)
    print("Status counts:", g['Result'].value_counts().to_dict())
    unv = g[g['Result'] == 'unverified']
    if not unv.empty:
        print("Unverified (no stats or snap-count evidence):", ', '.join(f"{r.Player} ({r.Team})" for r in unv.itertuples()))
    for res, label in (('void', 'Void (did not play)'), ('snap_count_zero', 'Played, graded on 0')):
        sub = g[g['Result'] == res] if res == 'void' else g[g['Basis'] == res]
        if not sub.empty:
            print(f"{label}:", ', '.join(f"{r.Player} {r.Stat} {r.Pick}" for r in sub.itertuples()))
    reports = []
    for label, by in [('overall', ['Week', 'Provenance']), ('stat+direction', ['Stat', 'Direction']),
                      ('position', ['Pos']), ('direction', ['Direction'])]:
        t = summarize(g, by)
        if t.empty:
            continue
        print(f"\n== {label} (hypothetical, 1u flat at listed odds) ==")
        print(t.to_string(index=False))
        reports.append(t.assign(Cut=label))
    if reports:
        pd.concat(reports).to_csv(OUT_DIR / 'report.csv', index=False)
    print(f"\nWrote {OUT_DIR.name}/graded_picks.csv, report.csv")


if __name__ == '__main__':
    main()
