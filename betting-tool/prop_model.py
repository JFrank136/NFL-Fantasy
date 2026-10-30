"""
Win-probability model for yardage / reception props.

The original ranking (projection minus line, as a % of the line) had no out-of-sample predictive power on the
graded record (see calibrate.py), and the market's median line beat the Draft Sharks projection on every stat.
So this model is anchored on the books and treats the projection as a small tilt. In log-odds of the OVER:

    z_mkt  = Z0 + B*(M - L)/S                    what the books' own prices say about line L
    z_skew = SHRINK * INTERCEPT[stat]            right-skew correction (books' implied over-probability runs high)
    z_proj = SHRINK * B * W * (Fair - M)/S       small tilt toward the Draft Sharks projection
    P(actual > L) = sigmoid(z_mkt + z_skew + z_proj);  P(under) = 1 - P(over)

Z0 is the consensus de-vigged log-odds of beating the median line M (each book's over/under pair is de-vigged
proportionally, moved to M with slope B, then averaged); S is the typical miss at that line level; Fair is the
projection mapped to a market-equivalent line. M and Z0 are computed from every book EXCEPT the one being bet
(leave-one-book-out), so a book's own quote can never vouch for itself.

Parameters are versioned and frozen under models/<version>/ (params.json + FROZEN.json with a hash). A frozen
version is never edited; refits go to a new version so later weeks are a genuine out-of-sample test.
"""
import hashlib
import json
import math
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent / 'models'
ACTIVE_MODEL = 'v1'
MIN_OTHER_BOOKS = 2   # fewer other books than this -> fall back to all books and say so


def params_sha(params):
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_params(version=ACTIVE_MODEL, models_dir=MODELS_DIR):
    """Load a model version; a frozen version whose params no longer match its recorded hash refuses to load."""
    d = Path(models_dir) / version
    params = json.loads((d / 'params.json').read_text())
    frozen = d / 'FROZEN.json'
    if frozen.exists() and json.loads(frozen.read_text())['params_sha256'] != params_sha(params):
        raise RuntimeError(f"models/{version}/params.json was modified after it was frozen; "
                           f"create a new version instead of editing a frozen one.")
    return params


def save_version(version, params, note='', models_dir=MODELS_DIR):
    """Write models/<version>/ and freeze it. Refuses to touch an existing version."""
    d = Path(models_dir) / version
    if d.exists():
        raise SystemExit(f"models/{version} already exists and is frozen; pick a new --version.")
    d.mkdir(parents=True)
    params = {**params, 'version': version}
    (d / 'params.json').write_text(json.dumps(params, indent=2))
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parent).stdout.strip()
    except OSError:
        commit = ''
    (d / 'FROZEN.json').write_text(json.dumps({
        'version': version, 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'params_sha256': params_sha(params), 'code_commit': commit, 'note': note}, indent=2))
    return d


def scale(stat, median, params):
    c0, c1 = params['scale'][stat]
    return c0 + c1 * median


def payout(odds):
    """Net units won on a winning 1-unit stake at American odds."""
    return odds / 100 if odds > 0 else 100 / -odds


def implied(odds):
    """Raw implied probability of American odds (includes the book's vig) = break-even hit rate."""
    return 1 / (1 + payout(odds))


break_even = implied


def ev_per_unit(p, odds):
    return p * payout(odds) - (1 - p)


def devig_over(over_odds, under_odds):
    """P(over) with the vig removed proportionally."""
    o, u = implied(over_odds), implied(under_odds)
    return o / (o + u)


def quotes_from_rows(rows):
    """rows: (book, side, line, odds) -> one quote per book: {'book','line','over','under'}. A book's two sides
    are only paired when they are at the same line; otherwise the unmatched side's price is dropped."""
    out = {}
    rows = list(rows)
    for book, side, line, odds in rows:
        if side == 'over':
            out.setdefault(book, {'book': book, 'line': line, 'over': odds, 'under': None})
    for book, side, line, odds in rows:
        if side == 'under':
            q = out.setdefault(book, {'book': book, 'line': line, 'over': None, 'under': None})
            if q['line'] == line:
                q['under'] = odds
    return list(out.values())


def market_logit(pairs, stat, median, params):
    """Consensus log-odds of beating `median` from (line, over_odds, under_odds) per book. 0.0 if none."""
    zs = []
    for line, over_odds, under_odds in pairs:
        p = min(max(devig_over(over_odds, under_odds), 0.01), 0.99)
        zs.append(math.log(p / (1 - p)) - params['b'] * (median - line) / scale(stat, median, params))
    return sum(zs) / len(zs) if zs else 0.0


def market_state(quotes, exclude_book, stat, params):
    """(median line M, Z0, books used, own_book_excluded) from `quotes`, leaving out `exclude_book`'s quote so
    the book being bet cannot influence its own fair value. Falls back to all books if too few remain."""
    use = [q for q in quotes if q['book'] != exclude_book]
    excluded = len(use) >= MIN_OTHER_BOOKS
    if not excluded:
        use = list(quotes)
    m = statistics.median(q['line'] for q in use)
    pairs = [(q['line'], q['over'], q['under']) for q in use if q['over'] is not None and q['under'] is not None]
    return m, market_logit(pairs, stat, m, params), len(use), excluded


def components(stat, line, median, fair, params, z0=0.0):
    """Log-odds contributions (over side): market, skew, projection."""
    s = scale(stat, median, params)
    z_mkt = z0 + params['b'] * (median - line) / s
    z_skew = params['shrink'] * params['intercept'][stat]
    z_proj = 0.0 if fair is None else params['shrink'] * params['b'] * params['w'] * (fair - median) / s
    return z_mkt, z_skew, z_proj


def _sig(z):
    return 1 / (1 + math.exp(-z))


def p_over(stat, line, median, fair, params, z0=0.0):
    """P(actual > line). `fair` None (no projection) -> market + skew only."""
    return _sig(sum(components(stat, line, median, fair, params, z0)))


def side_probs(direction, stat, line, median, fair, params, z0=0.0):
    """P(win) for the pick side, built up in three steps: market only, + skew, + projection (= the model)."""
    zm, zs, zp = components(stat, line, median, fair, params, z0)
    sgn = 1 if direction == 'O' else -1
    return {'p_mkt': _sig(sgn * zm), 'p_skew': _sig(sgn * (zm + zs)), 'p_full': _sig(sgn * (zm + zs + zp))}


def win_prob(direction, stat, line, median, fair, params, z0=0.0):
    return side_probs(direction, stat, line, median, fair, params, z0)['p_full']


def source_of_edge(mkt_pts, skew_pts, proj_pts, min_pts=1.0):
    """Where the estimated advantage comes from (probability points). Pricing = the book's price/line versus the
    other books (market probability minus break-even); Projection = the Draft Sharks tilt; Base-rate = skew only."""
    pricing, proj = mkt_pts >= min_pts, proj_pts >= min_pts
    if pricing and proj:
        return 'Pricing+Projection'
    if pricing:
        return 'Pricing'
    if proj:
        return 'Projection'
    return 'Base-rate' if skew_pts >= min_pts or mkt_pts + skew_pts + proj_pts > 0 else 'None'


def reliability_flags(stat, direction, line, median, raw_proj, fair, books, spread, odds, own_excluded=True):
    """Human-readable reasons a pick should not be trusted at face value (empty list = none found)."""
    f = []
    if books < 5:
        f.append(f'thin market ({books} books)')
    if not own_excluded:
        f.append('too few other books to price this independently')
    if raw_proj is not None and median > 0 and abs(raw_proj - median) / median > 0.25:
        f.append('projection >25% from market (role/injury/data error?)')
    if fair is not None and abs(fair - line) > 0.01 and ((fair > line) != (direction == 'O')):
        f.append('projection disagrees with pick side')
    if spread >= max(3.0, 0.08 * line):
        f.append('books disagree on line')
    if stat == 'Receptions' and direction == 'O' and odds > 0:
        f.append('plus-money reception over (weak record so far)')
    return f


def tier(ev_pct, flags, books, params):
    """Lean = model edge and nothing to doubt; Watch = edge but flagged/thin; Pass = no edge. Cutoffs are frozen."""
    t = params['tiers']
    if ev_pct >= t['lean_ev'] and not flags and books >= t['lean_min_books']:
        return 'Lean'
    return 'Watch' if ev_pct >= t['watch_ev'] else 'Pass'
