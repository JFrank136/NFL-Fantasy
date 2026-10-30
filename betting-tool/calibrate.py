#!/usr/bin/env python3
"""
Fit and validate the prop win-probability model on the graded universe (grades/universe.csv, see universe.py).

Leave-one-week-out: fit on all weeks but one, score the held-out week, so a model that only memorises a
week's quirks shows up as WORSE than a coin flip (log loss > 0.693). Prints the comparison, and with --write
saves the fitted parameters to data/model_params.json for prop_model.py to use.

Usage: python calibrate.py [--w 0.5] [--lam 10] [--write]
"""
import argparse
import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import prop_model
from prop_model import DEFAULT_PARAMS, PARAMS_FILE
from universe import OUT_FILE

MIN_LINE = {'Pass Yds': 100, 'Rush Yds': 15, 'Rec Yds': 15, 'Receptions': 1.5}  # calibrate on non-trivial lines
GRID_W = (0.0, 0.25, 0.5, 0.75, 1.0)
PS_KEY = ['Week', 'Player', 'Team', 'Stat']


def prepare(u, b_line):
    """Book-level rows with market median, market log-odds, projection->market 'fair', typical-miss scale and outcome."""
    u = u[u['Actual'].notna() & u['proj'].notna() & (u['proj'] > 0)].copy()
    u = u[[m >= MIN_LINE[s] for s, m in zip(u['Stat'], u['Median_Line'])]]
    ps = u.drop_duplicates(PS_KEY)
    fit = {s: np.polyfit(d['proj'], d['Median_Line'], 1) for s, d in ps.groupby('Stat')}
    scale = {}
    for s, d in ps.groupby('Stat'):
        c1, c0 = np.polyfit(d['Median_Line'], (d['Actual'] - d['Median_Line']).abs(), 1)
        scale[s] = [round(max(c0, 0.2), 3), round(max(c1, 0.0), 4)]
    params = {'b': b_line, 'scale': scale}
    # one row per book/line with both sides' prices -> de-vigged log-odds of that line, moved to the median line
    wide = u.pivot_table(index=PS_KEY + ['Book', 'Line'], columns='Side', values='Odds', aggfunc='first').dropna().reset_index()
    wide = wide.merge(ps[PS_KEY + ['Median_Line']], on=PS_KEY)
    z0 = {k: prop_model.market_logit(list(zip(g['Line'], g['over'], g['under'])), k[3], g['Median_Line'].iloc[0], params)
          for k, g in wide.groupby(PS_KEY)}
    u['Z0'] = [z0.get(tuple(r), 0.0) for r in u[PS_KEY].itertuples(index=False)]
    u['Fair'] = [np.polyval(fit[s], p) for s, p in zip(u['Stat'], u['proj'])]
    u['S'] = [scale[s][0] + scale[s][1] * m for s, m in zip(u['Stat'], u['Median_Line'])]
    u = u.drop_duplicates(PS_KEY + ['Book', 'Line'])  # over/under quote of one line = one event
    u = u[u['Line'] != u['Actual']].copy()
    u['over'] = (u['Actual'] > u['Line']).astype(int)
    u['wt'] = 1 / u.groupby(PS_KEY)['Line'].transform('size')  # each player-stat counts once
    u['base'] = u['Z0'] + b_line * (u['Median_Line'] - u['Line']) / u['S']  # market-only log-odds of this line
    return u, scale


def _tilt(d, w, b_line):
    return (b_line * w * (d['Fair'] - d['Median_Line']) / d['S']).values


def fit_intercepts(d, w, lam, stats, b_line):
    """Per-stat intercept on top of the market log-odds + projection tilt (ridge toward 0, strength lam)."""
    off, y, wt = d['base'].values + _tilt(d, w, b_line), d['over'].values, d['wt'].values
    si = np.array([stats.index(s) for s in d['Stat']])

    def nll(a):
        z = off + a[si]
        return -(wt * (y * -np.logaddexp(0, -z) + (1 - y) * -np.logaddexp(0, z))).sum() + 0.5 * lam * np.sum(a ** 2)

    return minimize(nll, np.zeros(len(stats)), method='L-BFGS-B').x


def predict(d, w, stats, a, b_line, shrink=1.0):
    """shrink scales the data-derived terms (intercept + tilt) only; the market's own log-odds stay at full weight."""
    z = d['base'].values + shrink * (_tilt(d, w, b_line) + a[[stats.index(s) for s in d['Stat']]])
    return 1 / (1 + np.exp(-z))


def logloss(d, p):
    p, y, wt = np.clip(p, 1e-4, 1 - 1e-4), d['over'].values, d['wt'].values
    return -(wt * (y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / wt.sum()


def cv(d, w, lam, stats, b_line, shrink=1.0):
    out = []
    for wk in sorted(d['Week'].unique()):
        tr, te = d[d['Week'] != wk], d[d['Week'] == wk]
        a = fit_intercepts(tr, w, lam, stats, b_line)
        out.append(logloss(te, predict(te, w, stats, a, b_line, shrink)))
    return float(np.mean(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--w', type=float, default=0.5, help='weight on the projection tilt (0 = market only)')
    ap.add_argument('--lam', type=float, default=10.0, help='ridge strength on per-stat intercepts')
    ap.add_argument('--write', action='store_true', help=f'save fitted params to {PARAMS_FILE.name}')
    args = ap.parse_args()
    b_line = DEFAULT_PARAMS['b']
    d, scale = prepare(pd.read_csv(OUT_FILE, parse_dates=['Start', 'captured_at']), b_line)
    stats = sorted(d['Stat'].unique())
    weeks = sorted(d['Week'].unique())
    ps = d.drop_duplicates(PS_KEY)
    print(f"{len(ps)} player-stats ({', '.join(f'wk{w}: {(ps.Week == w).sum()}' for w in weeks)}); {len(d)} line-events\n")
    print("Leave-one-week-out log loss (coin flip = 0.6931; lower is better):")
    zero = np.zeros(len(stats))
    print(f"  de-vigged market alone (no model terms):      {logloss(d, predict(d, 0, stats, zero, b_line)):.4f}")
    print(f"  market + projection tilt, no intercept:       " + ', '.join(
        f"w={w}: {logloss(d, predict(d, w, stats, zero, b_line)):.4f}" for w in GRID_W[1:]) + "  (no fitting)")
    for lam in (30.0, 10.0):
        for sh in (1.0, DEFAULT_PARAMS['shrink']):
            print(f"  + skew intercepts (ridge {lam:g}, shrink {sh}):  " + ', '.join(
                f"w={w}: {cv(d, w, lam, stats, b_line, sh):.4f}" for w in GRID_W))
    a = fit_intercepts(d, args.w, args.lam, stats, b_line)
    print(f"\nFit (w={args.w}, ridge={args.lam:g}): intercepts {dict(zip(stats, np.round(a, 2)))}")
    print("Typical-miss scale c0 + c1*line:", scale)
    print("\nDoes the projection add info beyond the line? corr(proj-line, actual-line) per stat:")
    for s, g in ps.groupby('Stat'):
        dev, res = g['proj'] - g['Median_Line'], g['Actual'] - g['Median_Line']
        r = np.corrcoef(dev, res)[0, 1]
        print(f"  {s:<11} n={len(g):>3}  r={r:+.3f} (noise +-{1 / np.sqrt(len(g)):.2f})  "
              f"MAE line={res.abs().mean():.2f}  MAE proj={(g['Actual'] - g['proj']).abs().mean():.2f}")
    if args.write:
        PARAMS_FILE.write_text(json.dumps({'w': args.w, 'b': b_line, 'shrink': DEFAULT_PARAMS['shrink'],
                                           'intercept': {s: round(float(v), 3) for s, v in zip(stats, a)},
                                           'scale': scale, 'weeks': [int(w) for w in weeks]}, indent=2))
        print(f"\nWrote {PARAMS_FILE}")


if __name__ == '__main__':
    main()
