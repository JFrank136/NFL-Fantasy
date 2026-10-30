#!/usr/bin/env python3
"""
Compare Draft Sharks stat projections to the best available prop line.

For every player/stat, find the best line a bettor could actually take:
  - Over : the LOWEST line among books whose over odds are >= MIN_ODDS (ties -> better odds)
  - Under: the HIGHEST line among books whose under odds are >= MIN_ODDS
then score it with prop_model.py (the frozen active model version): a market-anchored win probability -> EV at the
listed odds, plus reliability flags and a Lean/Watch/Pass tier. The fair value for a bet never uses the quote of the
book being bet (leave-one-book-out). Raw_Gap/Edge_* are the ORIGINAL model's numbers (projection minus line), kept for
reference and as a comparison baseline; they did not predict results (see calibrate.py).

Outputs: exports/prop_value.csv (active model, everything, sorted by EV), exports/prop_shortlist.csv (Lean + Watch),
exports/prop_predictions.csv (original, market-only and active models side by side, for scorecard.py).
Usage: python prop_value.py   |   python prop_value.py --explain "Player Name" [--stat "Rec Yds"]
"""
import argparse
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


def prep(lines, proj):
    lines, proj = lines.copy(), proj.copy()
    for df in (lines, proj):
        df['key'] = df['Player'].map(norm_name)
        df['TeamN'] = df['Team'].map(norm_team)
    return lines, proj.drop_duplicates(['key', 'TeamN'])


def slate_fit(lines, proj, log=print):
    """Per stat, straight-line fit of the median market line on the projection (projection -> market-equivalent line).
    Projections are means and lines sit near medians, so a raw projection runs above the line for everyone."""
    med = lines[lines['Side'] == 'over'].groupby(['key', 'TeamN', 'Stat'])['Line'].median().reset_index()
    med = med.merge(proj, on=['key', 'TeamN'])
    fit = {}
    for stat, col in STAT_COL.items():
        m = med[(med['Stat'] == stat) & (med[col] > 0) & (med['Line'] >= MIN_LINE[stat])]
        if len(m) < 10:  # market not posted (or too few matches) this week: skip the stat rather than crash
            log(f"Calibration {stat}: only {len(m)} matched rows; skipping this stat")
            continue
        fit[stat] = tuple(np.polyfit(m[col], m['Line'], 1))
        log(f"Calibration {stat}: line = {fit[stat][0]:.2f} x proj + {fit[stat][1]:.1f}  (n={len(m)})")
    return fit


def score_slate(lines, proj, params, hist=None, log=print):
    """Score every player/stat with three models on the same quotes. Returns (picks, unmatched).
    picks has one row per model per player/stat -- Model in {original, market_only, <version>} -- each model choosing
    its own side. The active-model rows carry the full detail (probability build-up, flags, tier, _trace)."""
    hist = hist or {}
    version = params['version']
    lines, proj = prep(lines, proj)
    fit = slate_fit(lines, proj, log)
    min_pts = params.get('source_min_pts', 1.0)
    rows, unmatched = [], set()
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
        fair = fit[stat][0] * raw + fit[stat][1]  # market-equivalent line for this projection
        n_books = grp['Book'].nunique()
        if n_books < MIN_BOOKS or fair <= 0:
            continue
        quotes = prop_model.quotes_from_rows(zip(grp['Book'], grp['Side'], grp['Line'], grp['Odds']))
        full_median = grp[grp['Side'] == 'over']['Line'].median()
        first = grp.iloc[0]
        cands = []
        for side in ('over', 'under'):
            b = best_line(grp, side)
            if b is None or b['Line'] < MIN_LINE[stat]:
                continue
            line, odds = float(b['Line']), int(b['Odds'])
            d = 'O' if side == 'over' else 'U'
            m, z0, n_used, excl = prop_model.market_state(quotes, b['Book'], stat, params)  # the bet's own book is left out
            pr = prop_model.side_probs(d, stat, line, m, fair, params, z0)
            edge = fair - line if side == 'over' else line - fair
            cands.append({'side': side, 'd': d, 'b': b, 'line': line, 'odds': odds, 'm': m, 'z0': z0, 'n_used': n_used,
                          'excl': excl, 'pr': pr, 'edge': edge, 'edge_pct': edge / line * 100,
                          'raw_gap': (raw - line) if side == 'over' else (line - raw),
                          'ev_mkt': 100 * prop_model.ev_per_unit(pr['p_mkt'], odds),
                          'ev': 100 * prop_model.ev_per_unit(pr['p_full'], odds)})
        if not cands:
            continue
        base = {'Week': int(first['Week']), 'Player': first['Player'], 'Pos': first['Pos'], 'Team': first['Team'],
                'Opp': first['Opp'], 'Stat': stat}

        def short(c, model, score, p, ev):
            return {**base, 'Model': model, 'Pick': f"{c['d']} {c['line']}", 'Odds': c['odds'], 'Book': c['b']['Book'],
                    'Score': round(score, 2), 'P_Win': None if p is None else round(p, 3),
                    'EV_Pct': None if ev is None else round(ev, 1)}

        o = max(cands, key=lambda c: c['edge_pct'])   # original model: biggest calibrated projection gap
        rows.append(short(o, 'original', 100 * o['raw_gap'] / o['line'], None, None))
        mo = max(cands, key=lambda c: c['ev_mkt'])    # market-only baseline: books' own prices, no projection/skew
        rows.append(short(mo, 'market_only', mo['ev_mkt'], mo['pr']['p_mkt'], mo['ev_mkt']))
        c = max(cands, key=lambda c: c['ev'])         # active model
        side_lines = grp[grp['Side'] == c['side']]
        spread = side_lines['Line'].max() - side_lines['Line'].min()
        flags = prop_model.reliability_flags(stat, c['d'], c['line'], c['m'], raw, fair, n_books, spread, c['odds'], c['excl'])
        pr, be = c['pr'], prop_model.break_even(c['odds'])
        mkt_pts = 100 * (pr['p_mkt'] - be)
        skew_pts = 100 * (pr['p_skew'] - pr['p_mkt'])
        proj_pts = 100 * (pr['p_full'] - pr['p_skew'])
        rows.append({**short(c, version, c['ev'], pr['p_full'], c['ev']),
                     'DS_Proj': round(raw, 1), 'Fair_Line': round(fair, 1),
                     'Raw_Gap': round(c['raw_gap'], 1), 'Edge_Yds': round(c['edge'], 1), 'Edge_Pct': round(c['edge_pct'], 1),
                     'Median_Line': full_median, 'Cons_Line': c['m'], 'Book_Spread': spread, 'Books': n_books,
                     'BreakEven': round(be, 3), 'P_Mkt': round(pr['p_mkt'], 3), 'EV_Mkt_Pct': round(c['ev_mkt'], 1),
                     'Mkt_Edge_Pts': round(mkt_pts, 1), 'Skew_Pts': round(skew_pts, 1), 'Proj_Pts': round(proj_pts, 1),
                     'Source': prop_model.source_of_edge(mkt_pts, skew_pts, proj_pts, min_pts),
                     'Tier': prop_model.tier(c['ev'], flags, n_books, params), 'Flags': '; '.join(flags),
                     'Hist': hist.get((stat, c['d']), ''),
                     '_trace': {'quotes': quotes, 'pick': c, 'raw': raw, 'fair': fair, 'stat': stat}})
    return pd.DataFrame(rows), unmatched


def explain(row, params):
    """Step-by-step arithmetic behind one active-model pick (a row of score_slate, with its _trace)."""
    t, c = row['_trace'], row['_trace']['pick']
    stat, line, odds, book, d = t['stat'], c['line'], c['odds'], c['b']['Book'], c['d']
    side_word = 'over' if d == 'O' else 'under'
    m = c['m']
    s = prop_model.scale(stat, m, params)
    zm, zs, zp = prop_model.components(stat, line, m, t['fair'], params, c['z0'])
    out = [f"{row['Player']} ({row['Team']} vs {row['Opp']}) {stat}: {row['Pick']} at {odds:+d} on {book}   [model {params['version']}]",
           f"1. Other books' prices (the bet's own book, {book}, is left out), each de-vigged and moved to the consensus line {m}:"]
    use = [q for q in t['quotes'] if q['book'] != book] if c['excl'] else t['quotes']
    for q in use:
        if q['over'] is None or q['under'] is None:
            out.append(f"     {q['book']:<11} {q['line']:>6}  (one side only; counts toward the median, not the price)")
            continue
        p = prop_model.devig_over(q['over'], q['under'])
        z = np.log(p / (1 - p)) - params['b'] * (m - q['line']) / s
        out.append(f"     {q['book']:<11} {q['line']:>6}  over {q['over']:+d} / under {q['under']:+d}  -> no-vig over {100 * p:.1f}%"
                   f"  -> log-odds at {m}: {z:+.3f}")
    out += [f"   Consensus line M = {m} (median of those books); Z0 = their average log-odds = {c['z0']:+.3f}",
            f"2. Typical miss S = {params['scale'][stat][0]} + {params['scale'][stat][1]} x {m} = {s:.1f}.  "
            f"Line credit = B x (M - L)/S = {params['b']} x ({m} - {line})/{s:.1f} = {params['b'] * (m - line) / s:+.3f}",
            f"   Market log-odds of OVER {line} = {zm:+.3f};  market P({side_word}) = {100 * c['pr']['p_mkt']:.1f}%",
            f"3. Skew correction = SHRINK {params['shrink']} x intercept[{stat}] {params['intercept'][stat]:+.3f} = {zs:+.3f}",
            f"4. Projection: DS {t['raw']:.1f} -> market-equivalent {t['fair']:.1f}; tilt = SHRINK x B x W x (Fair - M)/S = "
            f"{params['shrink']} x {params['b']} x {params['w']} x ({t['fair']:.1f} - {m})/{s:.1f} = {zp:+.3f}",
            f"5. Over log-odds {zm + zs + zp:+.3f}; P(win) for the {side_word} = {100 * c['pr']['p_full']:.1f}% "
            f"(market only {100 * c['pr']['p_mkt']:.1f}% -> +skew {100 * c['pr']['p_skew']:.1f}% -> +projection {100 * c['pr']['p_full']:.1f}%)",
            f"6. Break-even at {odds:+d} = {100 * prop_model.break_even(odds):.1f}%;  EV = {c['pr']['p_full']:.3f} x {prop_model.payout(odds):.3f}"
            f" - {1 - c['pr']['p_full']:.3f} = {row['EV_Pct']:+.1f}% per unit",
            f"7. Source of edge (probability points): pricing {row['Mkt_Edge_Pts']:+.1f}, skew {row['Skew_Pts']:+.1f}, "
            f"projection {row['Proj_Pts']:+.1f}  =>  {row['Source']};  tier {row['Tier']}"
            + (f";  flags: {row['Flags']}" if row['Flags'] else '')]
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--explain', metavar='PLAYER', help="print the arithmetic behind a player's pick(s); writes nothing")
    ap.add_argument('--stat', help='with --explain: limit to one stat, e.g. "Rec Yds"')
    args = ap.parse_args()
    params = prop_model.load_params()
    version = params['version']
    lines, proj = pd.read_csv('data/prop_lines.csv'), pd.read_csv('data/ds_projections.csv')
    picks, unmatched = score_slate(lines, proj, params, hist_records(), log=(lambda *_: None) if args.explain else print)
    act = picks[picks['Model'] == version].copy()
    if args.explain:
        hit = act[act['Player'].str.lower().str.contains(args.explain.lower())]
        if args.stat:
            hit = hit[hit['Stat'] == args.stat]
        for _, r in hit.iterrows():
            print(explain(r, params) + "\n")
        if hit.empty:
            print(f"No active-model pick found for {args.explain!r}.")
        return
    os.makedirs('exports', exist_ok=True)
    keep = ['Week', 'Model', 'Player', 'Pos', 'Team', 'Opp', 'Stat', 'Pick', 'Odds', 'Book', 'Score', 'P_Win', 'EV_Pct']
    picks[keep].to_csv('exports/prop_predictions.csv', index=False)
    out = act.drop(columns=['_trace']).sort_values('EV_Pct', ascending=False)
    out.to_csv('exports/prop_value.csv', index=False)
    short = out[out['Tier'].isin(['Lean', 'Watch'])]
    short = short.assign(_t=short['Tier'].ne('Lean')).sort_values(['_t', 'EV_Pct'], ascending=[True, False]).drop(columns='_t')
    short.to_csv('exports/prop_shortlist.csv', index=False)
    print(f"Wrote {len(out)} rows to exports/prop_value.csv (model {version}, odds >= {MIN_ODDS}, >= {MIN_BOOKS} books); "
          f"{len(short)} on exports/prop_shortlist.csv ({(out['Tier'] == 'Lean').sum()} Lean, {(out['Tier'] == 'Watch').sum()} Watch)")
    if unmatched:
        print(f"  {len(unmatched)} prop players had no Draft Sharks projection (e.g. {sorted(unmatched)[:5]})")
    print(f"\nNOTE: model {version} is frozen; out-of-sample results start with week {params.get('oos_from_week')} "
          "(python scorecard.py). Earlier weeks are in-sample. Check flags before betting.")
    print("Shortlist (Lean first, then by model EV; Lean = EV >= 3%, >= 5 books, no flags):")
    cols = ['Tier', 'Player', 'Team', 'Stat', 'Pick', 'Odds', 'Book', 'P_Win', 'BreakEven', 'EV_Pct', 'Source', 'Flags']
    print(short[cols].head(25).to_string(index=False) if len(short) else "  (none -- no pick clears the EV bar this week)")


if __name__ == "__main__":
    main()
