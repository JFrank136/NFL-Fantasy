#!/usr/bin/env python3
"""
Out-of-sample scorecard: the frozen active model vs the original model vs a market-only baseline.

Every saved live snapshot is replayed through all three models (prop_value.score_slate) using the frozen parameters in
models/<active>/, so nothing here is tuned to results. Each model's picks are graded against nflverse at the listed odds
under rules fixed in advance (the model's params.json): its top-N picks per week by its own score, plus its Lean/Watch
set (active) or its EV >= watch cutoff set (market-only). Weeks before params['oos_from_week'] were used to build the
model and are labelled in-sample -- they are context, not evidence. Also reported: performance by market and direction,
a v1-vs-market-only head-to-head on the bets where they differ, Brier scores, closing-line value, a check that the
scoring code is unchanged since the freeze, and whether the unattended closing capture is alive.

Usage: python scorecard.py   -> console tables; grades/scorecard.csv, scorecard_breakdown.csv, scorecard_h2h.csv
"""
import ast
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import prop_model
from grade import SNAP_DIR, grade, load_actuals, season_of, wilson
from prop_value import score_slate

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
    """Pre-registered pick sets: (model, label) -> boolean mask over `picks`."""
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


def avg_american(odds):
    """American odds equivalent of the average decimal price."""
    dec = float(np.mean([1 + prop_model.payout(o) for o in odds]))
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def summarize(g, label_cols):
    rows = []
    for k, grp in g.groupby(label_cols):
        k = k if isinstance(k, tuple) else (k,)
        w, l = int((grp['Result'] == 'win').sum()), int((grp['Result'] == 'loss').sum())
        n = w + l
        if not n:
            continue
        lo, hi = wilson(w, n)
        rows.append({**dict(zip(label_cols, k)), 'N': n, 'W': w, 'L': l, 'Hit%': round(100 * w / n, 1),
                     'CI95': f"{100 * lo:.0f}-{100 * hi:.0f}", 'BE%': round(100 * grp['Odds'].map(prop_model.break_even).mean(), 1),
                     'AvgOdds': avg_american(grp['Odds']), 'Units': round(grp['Units'].sum(), 1),
                     'ROI%': round(100 * grp['Units'].sum() / n, 1)})
    return pd.DataFrame(rows)


def head_to_head(graded, version, seed=0):
    """v1 vs market-only on the same player-stats. Identical bets (same side, line, book) cannot separate them, so the
    comparison that matters is the bets where they differ, plus the paired per-player-stat difference in units."""
    g = graded[graded['Result'].isin(['win', 'loss'])]
    key = ['Week', 'Player', 'Stat']
    j = g[g['Model'] == version].set_index(key).join(g[g['Model'] == 'market_only'].set_index(key),
                                                      lsuffix='_v', rsuffix='_m', how='inner')
    j['Same bet'] = (j['Pick_v'] == j['Pick_m']) & (j['Book_v'] == j['Book_m'])
    rng, rows = np.random.default_rng(seed), []
    for sample, x in j.groupby('Sample_v'):
        for label, sub in (('all', x), ('different bets only', x[~x['Same bet']])):
            if sub.empty:
                continue
            diff = (sub['Units_v'] - sub['Units_m']).values
            lo, hi = np.percentile([rng.choice(diff, len(diff)).mean() for _ in range(2000)], [2.5, 97.5])
            rows.append({'Sample': sample, 'Compared': label, 'N': len(sub),
                         f'{version} hit%': round(100 * (sub['Result_v'] == 'win').mean(), 1),
                         f'{version} ROI%': round(100 * sub['Units_v'].mean(), 1),
                         'mkt hit%': round(100 * (sub['Result_m'] == 'win').mean(), 1),
                         'mkt ROI%': round(100 * sub['Units_m'].mean(), 1),
                         'avg odds v/m': f"{avg_american(sub['Odds_v'])}/{avg_american(sub['Odds_m'])}",
                         'units diff/bet': round(diff.mean(), 3), 'CI95': f"{lo:+.2f}..{hi:+.2f}"})
    return pd.DataFrame(rows)


def _scoring_nodes(src):
    names = {'norm_name', 'norm_team', 'best_line', 'prep', 'slate_fit', 'score_slate',
             'MIN_ODDS', 'MIN_BOOKS', 'MIN_LINE', 'STAT_COL', 'TEAM_ALIAS', 'NICKNAMES'}
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef):
            name = n.name
        elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            name = n.targets[0].id
        else:
            continue
        if name in names:
            out[name] = ast.dump(n)
    return out


def frozen_code_status(version):
    """Compare the scoring code to the commit recorded when `version` was frozen (formatting and comments ignored)."""
    try:
        commit = json.loads((HERE / 'models' / version / 'FROZEN.json').read_text())['code_commit']

        def show(f):
            return subprocess.run(['git', 'show', f'{commit}:./{f}'], capture_output=True, text=True, cwd=HERE, check=True).stdout

        changed = []
        if ast.dump(ast.parse(show('prop_model.py'))) != ast.dump(ast.parse((HERE / 'prop_model.py').read_text(encoding='utf-8'))):
            changed.append('prop_model.py')
        a, b = _scoring_nodes(show('prop_value.py')), _scoring_nodes((HERE / 'prop_value.py').read_text(encoding='utf-8'))
        changed += [f'prop_value.py:{k}' for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        if changed:
            return f"CHANGED since freeze ({commit[:7]}): {', '.join(changed)} -- no longer a clean test of {version}"
        return f"OK -- scoring code matches the {version} freeze commit {commit[:7]}"
    except Exception as e:  # git missing, shallow clone, ...
        return f"could not verify ({type(e).__name__})"


def closing_health():
    """Is the unattended closing-line capture actually running?"""
    last = CLOSING_DIR / 'last_run.json'
    if not last.exists():
        return "closing capture: no heartbeat yet (is the PropClosingLines task running?)"
    h = json.loads(last.read_text())
    age = (datetime.now(timezone.utc) - pd.to_datetime(h['at_utc'], utc=True)).total_seconds() / 3600
    caps = len(list(CLOSING_DIR.glob('*/meta.json')))
    log = CLOSING_DIR / 'closing.log'
    errs = [ln for ln in log.read_text(encoding='utf-8').splitlines() if ' ERROR ' in ln] if log.exists() else []
    return (f"closing capture: last run {age:.1f}h ago ({h['outcome']}), {caps} captures saved, {len(errs)} logged errors"
            + (f" (latest: {errs[-1][:110]})" if errs else '') + ("  ** STALE: scheduler may not be running **" if age > 24 else ''))


def closing_value(picks, params):
    """Closing-line value for each pick that has a closing capture before its kickoff."""
    caps = []
    for f in sorted(CLOSING_DIR.glob('*/meta.json')):
        c = pd.read_csv(f.parent / 'prop_lines.csv')
        c['Start'] = pd.to_datetime(c['Start'], utc=True)
        caps.append((pd.to_datetime(json.loads(f.read_text())['captured_at_utc'], utc=True), c))
    rows = []
    for r in picks.to_dict('records'):
        usable = [(t, c) for t, c in caps if r['captured_at'] < t < r['Start']]
        if not usable:
            continue
        t, c = usable[-1]
        g = c[(c['Player'] == r['Player']) & (c['Stat'] == r['Stat']) & (c['Team'] == r['Team'])]
        if g.empty:
            continue
        quotes = prop_model.quotes_from_rows(zip(g['Book'], g['Side'], g['Line'], g['Odds']))
        m, z0, _, _ = prop_model.market_state(quotes, None, r['Stat'], params)  # all books: closing is a measurement
        d, line = r['Pick'].split()[0], float(r['Pick'].split()[1])
        p = prop_model.side_probs(d, r['Stat'], line, m, None, params, z0)['p_mkt']
        rows.append({'Model': r['Model'], 'Week': r['Week'], 'Player': r['Player'], 'Stat': r['Stat'], 'Pick': r['Pick'],
                     'Close_Median': m, 'Line_CLV': (m - line) if d == 'O' else (line - m),
                     'Close_P': round(p, 3), 'Close_EV_Pct': round(100 * prop_model.ev_per_unit(p, r['Odds']), 1)})
    return pd.DataFrame(rows)


def main():
    params = prop_model.load_params()
    version, oos = params['version'], params['oos_from_week']
    print(f"Model {version} (frozen); trained on weeks {params['trained_weeks']}; out-of-sample = week >= {oos}.")
    print("Frozen-code check:", frozen_code_status(version))
    print(closing_health(), "\n")
    picks = replay(params).reset_index(drop=True)
    sel = selections(picks, params)
    stats, snaps = load_actuals({season_of(s) for s in picks['Start']})
    graded = grade(picks.assign(DS_Proj=np.nan, Fair_Line=np.nan), stats, snaps)
    graded['Sample'] = np.where(graded['Week'] >= oos, 'OUT-OF-SAMPLE', 'in-sample')
    graded['Units'] = graded['Units'].astype(float)
    allg = pd.concat([graded[mask].assign(Model=model, Set=label) for (model, label), mask in sel.items()])
    order = {'original': 0, 'market_only': 1, version: 2}

    def sort(t, extra=()):
        t = t.assign(_o=t['Model'].map(order))
        return t.sort_values(['Sample', '_o', 'Set', *extra], ascending=[False, True, True] + [True] * len(extra)).drop(columns='_o')

    table = sort(summarize(allg, ['Sample', 'Model', 'Set']))
    print("Graded at listed odds, 1u flat (hypothetical). CI95 = Wilson interval on the hit rate; "
          "AvgOdds = American equivalent of the average price.")
    print(table.to_string(index=False))
    if not (graded['Sample'] == 'OUT-OF-SAMPLE').any():
        print(f"\nNo out-of-sample weeks yet: the first is week {oos}. Everything above is in-sample context, not evidence.")
    recommended = {('original', f"top {params['selection']['top_n']}/week"), (version, 'Lean+Watch'),
                   ('market_only', f"EV >= {params['tiers']['watch_ev']}%")}
    rec = allg[[(m, s) in recommended for m, s in zip(allg['Model'], allg['Set'])]].copy()
    rec['Market'] = rec['Stat'] + ' ' + rec['Pick'].str[0].map({'O': 'Over', 'U': 'Under'})
    breakdown = sort(summarize(rec, ['Sample', 'Model', 'Set', 'Market']), ['Market'])
    print("\nBy market and direction (each model's recommended set):")
    print(breakdown.to_string(index=False))
    h2h = head_to_head(graded, version)
    print("\nHead-to-head, v1 vs market-only on the same player-stats (identical bets cannot separate them):")
    print(h2h.to_string(index=False))
    pm = graded[graded['Model'].isin(['market_only', version]) & graded['Result'].isin(['win', 'loss'])].copy()
    pm['win'] = (pm['Result'] == 'win').astype(float)
    pm['P_Win'] = pm['P_Win'].astype(float)
    print("\nBrier score of P_Win over every candidate (lower is better; 0.25 = coin flip):")
    print(pm.groupby(['Sample', 'Model']).apply(
        lambda x: pd.Series({'N': len(x), 'Brier': round(((x['P_Win'] - x['win']) ** 2).mean(), 4)})).to_string())
    clv = closing_value(picks, params)
    if clv.empty:
        print("\nClosing-line value: no picks have a closing capture yet.")
    else:
        print(f"\nClosing-line value ({len(clv)} picks with a capture; positive = the market moved toward the pick):")
        print(clv.groupby('Model').agg(N=('Pick', 'size'), Line_CLV=('Line_CLV', 'mean'),
                                       Close_EV_Pct=('Close_EV_Pct', 'mean')).round(2).to_string())
    OUT_FILE.parent.mkdir(exist_ok=True)
    table.to_csv(OUT_FILE, index=False)
    breakdown.to_csv(OUT_FILE.with_name('scorecard_breakdown.csv'), index=False)
    h2h.to_csv(OUT_FILE.with_name('scorecard_h2h.csv'), index=False)
    print(f"\nWrote {OUT_FILE.relative_to(HERE)}, scorecard_breakdown.csv, scorecard_h2h.csv")


if __name__ == '__main__':
    main()
