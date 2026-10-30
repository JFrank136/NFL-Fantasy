"""
Win-probability model for yardage / reception props.

The old ranking (projection minus line, as a % of the line) had no out-of-sample predictive power on the
graded record (see calibrate.py), and the market's median line beat the Draft Sharks projection on every
stat. So this model is anchored on the market and treats the projection as a small tilt:

    Z0             = market's own de-vigged log-odds of beating the median line M, from every book's over/under prices
    center E       = M + W * (Fair - M)          Fair = projection mapped to a market line
    P(actual > L)  = sigmoid(Z0 + B*(M - L)/S + SHRINK * (INTERCEPT[stat] + B*(E - M)/S))

Z0 matters most for counts: an over priced +140 at a 2.5 line is a ~40% shot per the books, not 50%.
B*(M - L)/S credits a softer-than-consensus line. INTERCEPT is the skew correction (yardage is right-skewed, so
the books' implied over-probability runs high); S is the typical miss size at that line level. Parameters live in
data/model_params.json (written by `python calibrate.py --write`) with shrunk defaults below; they come from only
a few weeks of data. SHRINK scales only the two data-derived terms (intercept and projection tilt): leave-one-week-out
backtests show they have not yet separated good picks from marginal ones, so they should not claim confident edges.
"""
import json
import math
from pathlib import Path

PARAMS_FILE = Path(__file__).resolve().parent / 'data' / 'model_params.json'

DEFAULT_PARAMS = {
    'w': 0.5,
    'b': 1.2,
    'shrink': 0.5,
    'intercept': {'Pass Yds': 0.0, 'Rush Yds': -0.1, 'Rec Yds': -0.25, 'Receptions': -0.3},
    'scale': {'Pass Yds': [38.5, 0.028], 'Rush Yds': [13.3, 0.203], 'Rec Yds': [17.4, 0.147], 'Receptions': [1.23, 0.077]},
}


def load_params(path=PARAMS_FILE):
    params = json.loads(json.dumps(DEFAULT_PARAMS))
    try:
        saved = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return params
    for k, v in saved.items():
        if k in ('intercept', 'scale'):
            params[k].update(v)
        elif k in ('w', 'b', 'shrink'):
            params[k] = v
    return params


def scale(stat, median, params):
    c0, c1 = params['scale'][stat]
    return c0 + c1 * median


def implied(odds):
    """Raw implied probability of American odds (includes the book's vig)."""
    return 1 / (1 + payout(odds))


def devig_over(over_odds, under_odds):
    """P(over) with the vig removed proportionally."""
    o, u = implied(over_odds), implied(under_odds)
    return o / (o + u)


def market_logit(pairs, stat, median, params):
    """Consensus log-odds of beating `median`, from (line, over_odds, under_odds) per book. Each book's de-vigged
    price is moved to the median line with the model's line slope, then averaged. 0.0 if no book posts both sides."""
    zs = []
    for line, over_odds, under_odds in pairs:
        p = min(max(devig_over(over_odds, under_odds), 0.01), 0.99)
        zs.append(math.log(p / (1 - p)) - params['b'] * (median - line) / scale(stat, median, params))
    return sum(zs) / len(zs) if zs else 0.0


def p_over(stat, line, median, fair, params, z0=0.0):
    """P(actual > line). `fair` None (no projection) -> market-only. `z0` from market_logit()."""
    s = scale(stat, median, params)
    tilt = 0.0 if fair is None else params['w'] * (fair - median)
    z = z0 + params['b'] * (median - line) / s + params['shrink'] * (params['intercept'][stat] + params['b'] * tilt / s)
    return 1 / (1 + math.exp(-z))


def win_prob(direction, stat, line, median, fair, params, z0=0.0):
    p = p_over(stat, line, median, fair, params, z0)
    return p if direction == 'O' else 1 - p


def payout(odds):
    """Net units won on a winning 1-unit stake at American odds."""
    return odds / 100 if odds > 0 else 100 / -odds


def break_even(odds):
    return 1 / (1 + payout(odds))


def ev_per_unit(p, odds):
    return p * payout(odds) - (1 - p)


def reliability_flags(stat, direction, line, median, raw_proj, fair, books, spread, odds):
    """Human-readable reasons a pick should not be trusted at face value (empty list = none found)."""
    f = []
    if books < 5:
        f.append(f'thin market ({books} books)')
    if raw_proj is not None and median > 0 and abs(raw_proj - median) / median > 0.25:
        f.append('projection >25% from market (role/injury/data error?)')
    if fair is not None and abs(fair - line) > 0.01 and ((fair > line) != (direction == 'O')):
        f.append('projection disagrees with pick side')
    if spread >= max(3.0, 0.08 * line):
        f.append('books disagree on line')
    if stat == 'Receptions' and direction == 'O' and odds > 0:
        f.append('plus-money reception over (weak record so far)')
    return f


def tier(ev_pct, flags, books):
    """Lean = model edge and nothing to doubt; Watch = edge but flagged/thin; Pass = no edge."""
    if ev_pct >= 3.0 and not flags and books >= 5:
        return 'Lean'
    if ev_pct >= 1.5:
        return 'Watch'
    return 'Pass'
