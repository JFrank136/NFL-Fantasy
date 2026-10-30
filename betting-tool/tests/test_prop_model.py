import pytest

import prop_model as pm

PARAMS = {'w': 0.3, 'b': 1.0, 'shrink': 0.5,
          'intercept': {'Pass Yds': 0.0, 'Rush Yds': 0.0, 'Rec Yds': -0.2, 'Receptions': 0.0},
          'scale': {'Pass Yds': [40, 0], 'Rush Yds': [20, 0], 'Rec Yds': [20, 0], 'Receptions': [2, 0]}}


def test_payout_and_break_even():
    assert pm.payout(-110) == pytest.approx(100 / 110)
    assert pm.payout(150) == pytest.approx(1.5)
    assert pm.break_even(-110) == pytest.approx(110 / 210)
    assert pm.break_even(100) == pytest.approx(0.5)


def test_ev_is_zero_at_break_even_probability():
    for odds in (-130, -110, 100, 140):
        assert pm.ev_per_unit(pm.break_even(odds), odds) == pytest.approx(0)


def test_p_over_is_market_anchored_without_projection():
    # no projection and no skew -> a line at the median is a coin flip
    assert pm.p_over('Rush Yds', 50, 50, None, PARAMS) == pytest.approx(0.5)
    # lower line is easier to beat, higher is harder
    assert pm.p_over('Rush Yds', 40, 50, None, PARAMS) > 0.5 > pm.p_over('Rush Yds', 60, 50, None, PARAMS)


def test_projection_only_tilts_by_w_and_is_shrunk():
    full = pm.p_over('Rush Yds', 50, 50, 70, {**PARAMS, 'shrink': 1.0, 'w': 1.0})
    tilt = pm.p_over('Rush Yds', 50, 50, 70, PARAMS)
    assert 0.5 < tilt < full  # w and shrink both pull toward the market


def test_under_and_over_probabilities_sum_to_one():
    o = pm.win_prob('O', 'Rec Yds', 45.5, 44.5, 50, PARAMS)
    u = pm.win_prob('U', 'Rec Yds', 45.5, 44.5, 50, PARAMS)
    assert o + u == pytest.approx(1)


def test_skew_intercept_favours_unders_at_the_median():
    assert pm.win_prob('U', 'Rec Yds', 40, 40, None, PARAMS) > 0.5


def test_flags():
    ok = pm.reliability_flags('Rec Yds', 'U', 40.5, 40.0, 38, 37, 6, 1.0, -115)
    assert ok == []
    f = ' '.join(pm.reliability_flags('Rec Yds', 'O', 25.5, 25.5, 40, 36, 3, 4.0, -115))
    assert 'thin market' in f and 'projection >25%' in f and 'books disagree' in f
    assert 'disagrees' in ' '.join(pm.reliability_flags('Rec Yds', 'O', 45.5, 45.0, 40, 40, 6, 0, -115))
    assert 'plus-money' in ' '.join(pm.reliability_flags('Receptions', 'O', 3.5, 3.5, 4, 4, 6, 0, 130))


def test_tiers():
    assert pm.tier(4.0, [], 6) == 'Lean'
    assert pm.tier(4.0, ['x'], 6) == 'Watch'
    assert pm.tier(4.0, [], 4) == 'Watch'
    assert pm.tier(0.5, [], 6) == 'Pass'


def test_load_params_falls_back_to_defaults(tmp_path):
    assert pm.load_params(tmp_path / 'missing.json') == pm.DEFAULT_PARAMS
    p = tmp_path / 'p.json'
    p.write_text('{"w": 0.1, "intercept": {"Rec Yds": -0.5}}')
    got = pm.load_params(p)
    assert got['w'] == 0.1 and got['intercept']['Rec Yds'] == -0.5 and got['intercept']['Pass Yds'] == 0.0


def test_devig_removes_the_vig():
    assert pm.devig_over(-110, -110) == pytest.approx(0.5)
    p = pm.devig_over(140, -170)
    assert 0.35 < p < 0.42  # plus-money over is a longshot per the book


def test_market_logit_reads_prices_not_just_the_line():
    # same 2.5 line at every book, but the overs are priced +140: market says ~40%, not 50%
    pairs = [(2.5, 140, -170), (2.5, 150, -180)]
    z0 = pm.market_logit(pairs, 'Receptions', 2.5, PARAMS)
    assert pm.p_over('Receptions', 2.5, 2.5, None, {**PARAMS, 'shrink': 0}, z0) == pytest.approx(0.395, abs=0.03)
    assert pm.win_prob('O', 'Receptions', 2.5, 2.5, None, PARAMS, z0) < pm.break_even(140)  # no phantom edge


def test_market_logit_moves_each_books_price_to_the_median_line():
    # a book at 49.5 and one at 51.5 both pricing 50/50 imply the same market, centred at 50.5
    z0 = pm.market_logit([(49.5, -110, -110), (51.5, -110, -110)], 'Rush Yds', 50.5, PARAMS)
    assert z0 == pytest.approx(0, abs=1e-9)
    assert pm.market_logit([], 'Rush Yds', 50.5, PARAMS) == 0.0
