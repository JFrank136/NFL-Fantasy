#!/usr/bin/env python3
"""
Compare Draft Sharks stat projections to the best available prop line.

For every player/stat, find the best line a bettor could actually take:
  - Over : the LOWEST line among books whose over odds are >= MIN_ODDS (ties -> better odds)
  - Under: the HIGHEST line among books whose under odds are >= MIN_ODDS
then measure how far the projection sits from it (Raw_Gap = projection minus line, in the pick's direction;
Edge_* is the calibrated version, Book_Spread is the gap between books' lines). Config at the top.

Picks are chosen and ranked by prop_model.py: a market-anchored win probability -> EV at the listed odds, plus
reliability flags and a Lean/Watch/Pass tier. Raw_Gap/Edge_* are kept for reference but did NOT predict results
on the graded record (see calibrate.py). Output: exports/prop_value.csv (everything, sorted by EV) and
exports/prop_shortlist.csv (Lean + Watch only).
"""
import os
import re
import unicodedata

import numpy as np
import pandas as pd

import prop_model

MIN_ODDS = -130        # ignore juice worse than this (e.g. -145)
MIN_BOOKS = 2          # need at least this many books posting the player/stat
MIN_LINE = {'Pass Yds': 100, 'Rush Yds': 25, 'Rec Yds': 25, 'Receptions': 2.5}  # skip tiny lines (noisy % edges)
STAT_COL = {'Pass Yds': 'pass_yds', 'Rush Yds': 'rush_yds', 'Rec Yds': 'rec_yds', 'Receptions': 'rec_catch'}
TEAM_ALIAS = {'WAS': 'WSH', 'JAC': 'JAX', 'LA': 'LAR', 'ARZ': 'ARI', 'BLT': 'BAL', 'CLV': 'CLE', 'HST': 'HOU'}


NICKNAMES = {'cam': 'cameron', 'josh': 'joshua', 'mike': 'michael', 'chris': 'christopher', 'matt': 'matthew',
             'zach': 'zachary', 'nick': 'nicholas', 'tim': 'timothy', 'dj': 'dj', 'ken': 'kenneth', 'will': 'william'}


def norm_name(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'`-]", '', s)
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    first, _, rest = s.partition(' ')
    return f"{NICKNAMES.get(first, first)} {rest}".strip()


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


def hist_records(path='grades/graded_picks.csv'):
    """'W-L (hit%)' per stat+direction from the graded pick history, shown next to each pick for context."""
    try:
        g = pd.read_csv(path)
    except OSError:
        return {}
    g = g[g['Result'].isin(['win', 'loss'])]
    out = {}
    for (stat, d), grp in g.groupby(['Stat', 'Direction']):
        w = int((grp['Result'] == 'win').sum())
        out[(stat, d)] = f"{w}-{len(grp) - w} ({100 * w / len(grp):.0f}%)"
    return out


def main():
    params = prop_model.load_params()
    hist = hist_records()
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
        if len(m) < 10:  # market not posted (or too few matches) this week: skip the stat rather than crash
            print(f"Calibration {stat}: only {len(m)} matched rows; skipping this stat")
            continue
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
        if stat not in fit:
            continue
        raw = float(p.iloc[0][STAT_COL[stat]])
        projection = fit[stat][0] * raw + fit[stat][1]  # market-equivalent line for this projection
        n_books = grp['Book'].nunique()
        if n_books < MIN_BOOKS or projection <= 0:
            continue
        consensus = grp[grp['Side'] == 'over']['Line'].median()
        wide = grp.pivot_table(index=['Book', 'Line'], columns='Side', values='Odds', aggfunc='first').dropna().reset_index()
        z0 = prop_model.market_logit(list(zip(wide['Line'], wide['over'], wide['under'])), stat, consensus, params)
        cands = []
        for side in ('over', 'under'):
            b = best_line(grp, side)
            if b is None or b['Line'] < MIN_LINE[stat]:
                continue
            edge = projection - b['Line'] if side == 'over' else b['Line'] - projection
            direction = 'O' if side == 'over' else 'U'
            p_win = prop_model.win_prob(direction, stat, float(b['Line']), consensus, projection, params, z0)
            ev = 100 * prop_model.ev_per_unit(p_win, b['Odds'])
            cands.append((ev, edge / b['Line'] * 100, edge, side, b, p_win))
        if not cands:
            continue
        # take the side with the better EV (not the bigger projection gap, which did not predict results)
        ev, pct, edge, side, b, p_win = max(cands, key=lambda c: c[0])
        direction = 'O' if side == 'over' else 'U'
        # spread between books on the pick's side (over: lowest vs highest line posted)
        side_lines = grp[grp['Side'] == side]
        spread = side_lines['Line'].max() - side_lines['Line'].min()
        raw_gap = (raw - b['Line']) if side == 'over' else (b['Line'] - raw)
        first = grp.iloc[0]
        flags = prop_model.reliability_flags(stat, direction, float(b['Line']), consensus, raw, projection,
                                             n_books, spread, int(b['Odds']))
        rows.append({
            'Player': first['Player'], 'Pos': first['Pos'], 'Team': first['Team'], 'Opp': first['Opp'],
            'Stat': stat, 'Pick': f"{'O' if side == 'over' else 'U'} {b['Line']}",
            'Odds': int(b['Odds']), 'Book': b['Book'], 'DS_Proj': round(raw, 1), 'Fair_Line': round(projection, 1),
            'Raw_Gap': round(raw_gap, 1), 'Edge_Yds': round(edge, 1), 'Edge_Pct': round(pct, 1),
            'Median_Line': consensus, 'Book_Spread': spread, 'Books': n_books, 'Week': int(first['Week']),
            'P_Win': round(p_win, 3), 'BreakEven': round(prop_model.break_even(int(b['Odds'])), 3),
            'EV_Pct': round(ev, 1), 'Tier': prop_model.tier(ev, flags, n_books), 'Flags': '; '.join(flags),
            'Hist': hist.get((stat, direction), ''),
        })

    out = pd.DataFrame(rows).sort_values('EV_Pct', ascending=False)
    os.makedirs('exports', exist_ok=True)
    out.to_csv('exports/prop_value.csv', index=False)
    short = out[out['Tier'].isin(['Lean', 'Watch'])]
    short = short.assign(_t=short['Tier'].ne('Lean')).sort_values(['_t', 'EV_Pct'], ascending=[True, False]).drop(columns='_t')
    short.to_csv('exports/prop_shortlist.csv', index=False)
    print(f"Wrote {len(out)} rows to exports/prop_value.csv (odds >= {MIN_ODDS}, >= {MIN_BOOKS} books); "
          f"{len(short)} on exports/prop_shortlist.csv ({(out['Tier'] == 'Lean').sum()} Lean, {(out['Tier'] == 'Watch').sum()} Watch)")
    if unmatched:
        print(f"  {len(unmatched)} prop players had no Draft Sharks projection (e.g. {sorted(unmatched)[:5]})")
    print("\nNOTE: early-stage model. Leave-one-week-out backtest on 2 weeks of lines (calibrate.py): Lean+Watch +7% ROI on "
          "~90 bets -- encouraging, but not statistically distinguishable from zero. Check flags before betting.")
    print("Shortlist (Lean first, then by model EV; Lean = EV >= 3%, >= 5 books, no flags):")
    cols = ['Tier', 'Player', 'Team', 'Stat', 'Pick', 'Odds', 'Book', 'P_Win', 'BreakEven', 'EV_Pct', 'Flags']
    print(short[cols].head(25).to_string(index=False) if len(short) else "  (none -- no pick clears the EV bar this week)")


if __name__ == "__main__":
    main()
