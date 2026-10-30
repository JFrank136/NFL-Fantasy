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
from universe import OUT_FILE

MIN_LINE = {'Pass Yds': 100, 'Rush Yds': 15, 'Rec Yds': 15, 'Receptions': 1.5}  # calibrate on non-trivial lines
GRID_W = (0.0, 0.25, 0.5, 0.75, 1.0)
# Fixed (not tuned further) hyperparameters of a new model version; only the intercepts and scale are fitted.
B_LINE, SHRINK = 1.2, 0.5
TIERS = {'lean_ev': 3.0, 'watch_ev': 1.5, 'lean_min_books': 5}
SELECTION = {'top_n': 20}   # scorecard.py compares models on each one's top-N per week and on its Lean/Watch set
PS_KEY = ['Week', 'Player', 'Team', 'Stat']


def prepare(u, b_line):
    """Book-level rows with leave-this-book-out market median/log-odds, projection->market 'fair', scale, outcome."""
    u = u[u['Actual'].notna() & u['proj'].notna() & (u['proj'] > 0)].copy()
    u = u[[m >= MIN_LINE[s] for s, m in zip(u['Stat'], u['Median_Line'])]]
    ps = u.drop_duplicates(PS_KEY)
    fit = {s: np.polyfit(d['proj'], d['Median_Line'], 1) for s, d in ps.groupby('Stat')}
    scale = {}
    for s, d in ps.groupby('Stat'):
        c1, c0 = np.polyfit(d['Median_Line'], (d['Actual'] - d['Median_Line']).abs(), 1)
        scale[s] = [round(max(c0, 0.2), 3), round(max(c1, 0.0), 4)]
    params = {'b': b_line, 'scale': scale}
    rows = []
    for key, g in u.groupby(PS_KEY):
        quotes = prop_model.quotes_from_rows(zip(g['Book'], g['Side'], g['Line'], g['Odds']))
        stat = key[3]
        for book, line in g[['Book', 'Line']].drop_duplicates().itertuples(index=False):
            m, z0, _, _ = prop_model.market_state(quotes, book, stat, params)  # the book being scored is left out
            rows.append(key + (book, line, m, z0))
    loo = pd.DataFrame(rows, columns=PS_KEY + ['Book', 'Line', 'M', 'Z0'])
    u = u.drop_duplicates(PS_KEY + ['Book', 'Line']).merge(loo, on=PS_KEY + ['Book', 'Line'])  # one event per line
    u['Fair'] = [np.polyval(fit[s], p) for s, p in zip(u['Stat'], u['proj'])]
    u['S'] = [scale[s][0] + scale[s][1] * m for s, m in zip(u['Stat'], u['M'])]
    u = u[u['Line'] != u['Actual']].copy()
    u['over'] = (u['Actual'] > u['Line']).astype(int)
    u['wt'] = 1 / u.groupby(PS_KEY)['Line'].transform('size')  # each player-stat counts once
    u['base'] = u['Z0'] + b_line * (u['M'] - u['Line']) / u['S']  # market-only log-odds of this line
    return u, scale


def _tilt(d, w, b_line):
    return (b_line * w * (d['Fair'] - d['M']) / d['S']).values


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
    ap.add_argument('--lam', type=float, default=30.0, help='ridge strength on per-stat intercepts')
    ap.add_argument('--version', help='with --write: save as a NEW frozen model version under models/<version>/')
    ap.add_argument('--write', action='store_true', help='freeze the fitted params as --version (never overwrites)')
    args = ap.parse_args()
    b_line = B_LINE
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
        for sh in (1.0, SHRINK):
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
        if not args.version:
            raise SystemExit("--write needs --version (e.g. v2); frozen versions are never overwritten.")
        d = prop_model.save_version(args.version, {
            'w': args.w, 'b': b_line, 'shrink': SHRINK, 'ridge': args.lam,
            'intercept': {s: round(float(v), 3) for s, v in zip(stats, a)}, 'scale': scale,
            'tiers': TIERS, 'selection': SELECTION, 'source_min_pts': 1.0,
            'trained_weeks': [int(w) for w in weeks], 'oos_from_week': int(max(weeks)) + 1},
            note='fitted by calibrate.py on leave-one-book-out features')
        print(f"\nFroze {d}  (out-of-sample from week {int(max(weeks)) + 1})")


if __name__ == '__main__':
    main()
