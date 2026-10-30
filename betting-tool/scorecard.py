#!/usr/bin/env python3
"""
Out-of-sample scorecard: the frozen active model vs the original model vs a market-only baseline.

Every saved live snapshot is replayed through all three models (prop_value.score_slate) using the frozen parameters in
models/<active>/, so nothing here is tuned to results. Each model's picks are graded against nflverse at the listed odds
under rules fixed in advance (the model's params.json): its top-N picks per week by its own score, plus its Lean/Watch
set (active) or its EV >= watch cutoff set (market-only). Weeks before params['oos_from_week'] were used to build the
model and are labelled in-sample -- they are context, not evidence. Closing-line value is reported for any picks that
have a closing capture (closing.py).

Usage: python scorecard.py        -> console tables, grades/scorecard.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import prop_model
from grade import SNAP_DIR, grade, load_actuals, season_of, wilson
from prop_value import norm_name, norm_team, score_slate

HERE = Path(__file__).resolve().parent
CLOSING_DIR = HERE / 'closing'
OUT_FILE = HERE / 'grades' / 'scorecard.csv'


def replay(params, snap_dir=SNAP_DIR):
    """Latest pre-kickoff scoring per week/player/stat/model across all live snapshots."""
    frames = []
    for meta_file in sorted(Path(snap_dir).glob('*/meta.json')):
        meta, d = json.loads(meta_file.read_text()), meta_file.parent
        if meta.get('provenance') == 'imported' or not (d / 'prop_lines.csv').exists():
            continue
        lines, proj = pd.read_csv(d / 'prop_lines.csv'), pd.read_csv(d / 'ds_projections.csv')
        lines['Start'] = pd.to_datetime(lines['Start'], utc=True)
        captured = pd.to_datetime(meta['captured_at_utc'], utc=True)
        lines = lines[captured < lines['Start']]
        if lines.empty:
            continue
        picks, _ = score_slate(lines, proj, params, log=lambda *_: None)
        start = lines.groupby(['Player', 'Team', 'Stat'])['Start'].min().rename('Start').reset_index()
        picks = picks.drop(columns=['_trace']).merge(start, on=['Player', 'Team', 'Stat'], how='left')
        frames.append(picks.assign(captured_at=captured, snapshot=d.name))
    if not frames:
        raise SystemExit("No live snapshots to replay.")
    allp = pd.concat(frames, ignore_index=True).sort_values('captured_at')
    return allp.drop_duplicates(['Week', 'Player', 'Stat', 'Model'], keep='last')


def selections(picks, params):
    """Pre-registered pick sets: label -> boolean mask over `picks`."""
    top_n, t = params['selection']['top_n'], params['tiers']
    out = {}
    for model, g in picks.groupby('Model'):
        top = g.sort_values('Score', ascending=False).groupby('Week').head(top_n)
        out[(model, f'top {top_n}/week')] = picks.index.isin(top.index)
        out[(model, 'all picks')] = (picks['Model'] == model).values
    active = picks['Model'] == params['version']
    out[(params['version'], 'Lean+Watch')] = (active & picks['Tier'].isin(['Lean', 'Watch'])).values
    out[(params['version'], 'Lean only')] = (active & (picks['Tier'] == 'Lean')).values
    mo = picks['Model'] == 'market_only'
    out[('market_only', f"EV >= {t['watch_ev']}%")] = (mo & (picks['EV_Pct'] >= t['watch_ev'])).values
    return out


def summarize(g, label_cols):
    rows = []
    for k, grp in g.groupby(label_cols):
        w, l = int((grp['Result'] == 'win').sum()), int((grp['Result'] == 'loss').sum())
        n = w + l
        if not n:
            continue
        lo, hi = wilson(w, n)
        rows.append({**dict(zip(label_cols, k)), 'N': n, 'W': w, 'L': l, 'Hit%': round(100 * w / n, 1),
                     'CI95': f"{100 * lo:.0f}-{100 * hi:.0f}",
                     'BE%': round(100 * grp['Odds'].map(prop_model.break_even).mean(), 1),
                     'Units': round(grp['Units'].sum(), 1), 'ROI%': round(100 * grp['Units'].sum() / n, 1)})
    return pd.DataFrame(rows)


def closing_value(picks, params):
    """Closing-line value for each pick that has a closing capture before its kickoff."""
    caps = []
    for f in sorted(CLOSING_DIR.glob('*/meta.json')):
        d = f.parent
        c = pd.read_csv(d / 'prop_lines.csv')
        c['Start'] = pd.to_datetime(c['Start'], utc=True)
        caps.append((pd.to_datetime(json.loads(f.read_text())['captured_at_utc'], utc=True), c))
    rows = []
    for r in picks.to_dict('records'):
        usable = [(t, c) for t, c in caps if t < r['Start'] and t > r['captured_at']]
        if not usable:
            continue
        t, c = usable[-1]
        g = c[(c['Player'] == r['Player']) & (c['Stat'] == r['Stat']) & (c['Team'] == r['Team'])]
        if g.empty:
            continue
        quotes = prop_model.quotes_from_rows(zip(g['Book'], g['Side'], g['Line'], g['Odds']))
        m, z0, _, _ = prop_model.market_state(quotes, None, r['Stat'], params)  # all books: closing is a measurement
        d, line = r['Pick'].split()[0], float(r['Pick'].split()[1])
        p = prop_model.side_probs(d, r['Stat'], line, m, None, {**params, 'intercept': {r['Stat']: 0.0}}, z0)['p_mkt']
        rows.append({'Model': r['Model'], 'Week': r['Week'], 'Player': r['Player'], 'Stat': r['Stat'], 'Pick': r['Pick'],
                     'Close_Median': m, 'Line_CLV': (m - line) if d == 'O' else (line - m),
                     'Close_P': round(p, 3), 'Close_EV_Pct': round(100 * prop_model.ev_per_unit(p, r['Odds']), 1)})
    return pd.DataFrame(rows)


def main():
    params = prop_model.load_params()
    version, oos = params['version'], params['oos_from_week']
    print(f"Model {version} (frozen); trained on weeks {params['trained_weeks']}; out-of-sample = week >= {oos}.\n")
    picks = replay(params).reset_index(drop=True)
    sel = selections(picks, params)
    stats, snaps = load_actuals({season_of(s) for s in picks['Start']})
    graded = grade(picks.assign(DS_Proj=np.nan, Fair_Line=np.nan), stats, snaps)
    graded['Sample'] = np.where(graded['Week'] >= oos, 'OUT-OF-SAMPLE', 'in-sample')
    graded['Units'] = graded['Units'].astype(float)
    rows = []
    for (model, label), mask in sel.items():
        sub = graded[mask].assign(Model=model, Set=label)
        rows.append(sub)
    allg = pd.concat(rows)
    table = summarize(allg, ['Sample', 'Model', 'Set'])
    order = {'original': 0, 'market_only': 1, version: 2}
    table = table.assign(_o=table['Model'].map(order)).sort_values(['Sample', '_o', 'Set'], ascending=[False, True, True]).drop(columns='_o')
    print("Graded at listed odds, 1u flat (hypothetical). CI95 is the Wilson interval on the hit rate.")
    print(table.to_string(index=False))
    if not (graded['Sample'] == 'OUT-OF-SAMPLE').any():
        print(f"\nNo out-of-sample weeks yet: the first is week {oos}. The in-sample rows above are context only.")
    # probability quality of the two probability models, on every candidate pick
    pm = graded[graded['Model'].isin(['market_only', version]) & graded['Result'].isin(['win', 'loss'])].copy()
    pm['win'] = (pm['Result'] == 'win').astype(float)
    pm['P_Win'] = pm['P_Win'].astype(float)
    print("\nBrier score of P_Win over every candidate (lower is better; 0.25 = coin flip):")
    print(pm.groupby(['Sample', 'Model']).apply(lambda x: pd.Series({'N': len(x), 'Brier': round(((x['P_Win'] - x['win']) ** 2).mean(), 4)})).to_string())
    clv = closing_value(picks, params)
    if clv.empty:
        print("\nClosing-line value: no closing captures yet (run closing.py shortly before kickoffs).")
    else:
        print("\nClosing-line value (picks with a closing capture; positive = the market moved toward the pick):")
        print(clv.groupby('Model').agg(N=('Pick', 'size'), Line_CLV=('Line_CLV', 'mean'),
                                       Close_EV_Pct=('Close_EV_Pct', 'mean')).round(2).to_string())
    OUT_FILE.parent.mkdir(exist_ok=True)
    table.to_csv(OUT_FILE, index=False)
    print(f"\nWrote {OUT_FILE.relative_to(HERE)}")


if __name__ == '__main__':
    main()
