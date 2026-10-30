import json

import pandas as pd
import pytest

import prop_model as pm
import prop_value as pv

PARAMS = {'version': 'vt', 'w': 0.5, 'b': 1.2, 'shrink': 0.5, 'ridge': 30,
          'intercept': {'Pass Yds': 0.0, 'Rush Yds': 0.0, 'Rec Yds': -0.2, 'Receptions': 0.0},
          'scale': {'Pass Yds': [40, 0], 'Rush Yds': [20, 0], 'Rec Yds': [20, 0], 'Receptions': [2, 0]},
          'tiers': {'lean_ev': 3.0, 'watch_ev': 1.5, 'lean_min_books': 5}, 'selection': {'top_n': 20},
          'source_min_pts': 1.0, 'trained_weeks': [6, 7], 'oos_from_week': 8}


def test_payout_and_break_even():
    assert pm.payout(-110) == pytest.approx(100 / 110)
    assert pm.payout(150) == pytest.approx(1.5)
    assert pm.break_even(-110) == pytest.approx(110 / 210)
    assert pm.break_even(100) == pytest.approx(0.5)
    assert pm.break_even(150) == pytest.approx(0.4)


def test_ev_is_zero_at_break_even_probability():
    for odds in (-130, -110, 100, 140):
        assert pm.ev_per_unit(pm.break_even(odds), odds) == pytest.approx(0)


def test_ev_hand_check():
    # 55% at -110: 0.55 * 0.9091 - 0.45 = +5.0% per unit
    assert pm.ev_per_unit(0.55, -110) == pytest.approx(0.05, abs=1e-3)
    # 45% at +140: 0.45 * 1.4 - 0.55 = +8.0%
    assert pm.ev_per_unit(0.45, 140) == pytest.approx(0.08, abs=1e-3)


def test_devig_removes_the_vig():
    assert pm.devig_over(-110, -110) == pytest.approx(0.5)
    p = pm.devig_over(140, -170)
    assert 0.35 < p < 0.42  # plus-money over is a longshot per the book
    # de-vigged probabilities of the two sides sum to one by construction
    assert pm.devig_over(-130, 105) + (1 - pm.devig_over(-130, 105)) == pytest.approx(1)
    assert pm.implied(-130) + pm.implied(105) > 1  # the vig that was removed


def test_market_only_without_signal_is_a_coin_flip():
    z = pm.components('Rush Yds', 50, 50, None, PARAMS, 0.0)
    assert sum(z) == pytest.approx(0)
    assert pm.p_over('Rush Yds', 40, 50, None, PARAMS) > 0.5 > pm.p_over('Rush Yds', 60, 50, None, PARAMS)


def test_probability_build_up_and_sides():
    over = pm.side_probs('O', 'Rec Yds', 45.5, 44.5, 50, PARAMS, 0.1)
    under = pm.side_probs('U', 'Rec Yds', 45.5, 44.5, 50, PARAMS, 0.1)
    for k in over:
        assert over[k] + under[k] == pytest.approx(1)
    assert over['p_skew'] < over['p_mkt']   # negative skew intercept lowers the over
    assert over['p_full'] > over['p_skew']  # projection (50 vs 44.5) pushes the over back up
    assert pm.win_prob('O', 'Rec Yds', 45.5, 44.5, 50, PARAMS, 0.1) == pytest.approx(over['p_full'])


def test_projection_tilt_is_damped():
    full = pm.p_over('Rush Yds', 50, 50, 70, {**PARAMS, 'shrink': 1.0, 'w': 1.0})
    tilt = pm.p_over('Rush Yds', 50, 50, 70, PARAMS)
    assert 0.5 < tilt < full


def test_market_logit_reads_prices_not_just_the_line():
    pairs = [(2.5, 140, -170), (2.5, 150, -180)]   # +140 overs at a 2.5 line: books say ~40%
    z0 = pm.market_logit(pairs, 'Receptions', 2.5, PARAMS)
    assert pm.p_over('Receptions', 2.5, 2.5, None, {**PARAMS, 'shrink': 0}, z0) == pytest.approx(0.395, abs=0.03)
    assert pm.win_prob('O', 'Receptions', 2.5, 2.5, None, PARAMS, z0) < pm.break_even(140)  # no phantom edge


def test_market_logit_moves_each_books_price_to_the_median_line():
    z0 = pm.market_logit([(49.5, -110, -110), (51.5, -110, -110)], 'Rush Yds', 50.5, PARAMS)
    assert z0 == pytest.approx(0, abs=1e-9)
    assert pm.market_logit([], 'Rush Yds', 50.5, PARAMS) == 0.0


def rows(book, line, over, under):
    return [(book, 'over', line, over), (book, 'under', line, under)]


def test_quotes_pair_sides_only_at_the_same_line():
    q = {x['book']: x for x in pm.quotes_from_rows(rows('A', 40.5, -110, -110) + [('B', 'over', 40.5, -115), ('B', 'under', 41.5, -105)])}
    assert q['A']['under'] == -110
    assert q['B']['over'] == -115 and q['B']['under'] is None


def test_own_book_cannot_influence_its_own_fair_value():
    base = rows('A', 40.5, -110, -110) + rows('B', 41.5, -110, -110) + rows('C', 40.5, -105, -125) + rows('D', 41.5, -120, 100)
    q1 = pm.quotes_from_rows(base)
    # change ONLY book D's quote drastically; the fair value used to bet at D must not move
    q2 = pm.quotes_from_rows([r for r in base if r[0] != 'D'] + rows('D', 30.5, -300, 220))
    s1 = pm.market_state(q1, 'D', 'Rec Yds', PARAMS)
    s2 = pm.market_state(q2, 'D', 'Rec Yds', PARAMS)
    assert s1 == s2 and s1[3] is True
    # ...whereas the all-books view does move (so the exclusion is doing real work)
    assert pm.market_state(q1, None, 'Rec Yds', PARAMS)[:2] != pm.market_state(q2, None, 'Rec Yds', PARAMS)[:2]


def test_market_state_falls_back_when_too_few_other_books():
    q = pm.quotes_from_rows(rows('A', 40.5, -110, -110) + rows('B', 41.5, -110, -110))
    m, z0, n, excluded = pm.market_state(q, 'A', 'Rec Yds', PARAMS)
    assert excluded is False and n == 2 and m == 41.0
    assert 'too few other books' in ' '.join(pm.reliability_flags('Rec Yds', 'O', 40.5, m, 40, 40, 6, 0, -110, excluded))


def test_source_of_edge():
    assert pm.source_of_edge(2.0, 0.1, 0.2) == 'Pricing'
    assert pm.source_of_edge(0.0, 0.3, 1.5) == 'Projection'
    assert pm.source_of_edge(2.0, 0.0, 1.5) == 'Pricing+Projection'
    assert pm.source_of_edge(-1.0, 1.5, 0.2) == 'Base-rate'
    assert pm.source_of_edge(-3.0, -0.5, -0.2) == 'None'


def test_flags():
    assert pm.reliability_flags('Rec Yds', 'U', 40.5, 40.0, 38, 37, 6, 1.0, -115) == []
    f = ' '.join(pm.reliability_flags('Rec Yds', 'O', 25.5, 25.5, 40, 36, 3, 4.0, -115))
    assert 'thin market' in f and 'projection >25%' in f and 'books disagree' in f
    assert 'disagrees' in ' '.join(pm.reliability_flags('Rec Yds', 'O', 45.5, 45.0, 40, 40, 6, 0, -115))
    assert 'plus-money' in ' '.join(pm.reliability_flags('Receptions', 'O', 3.5, 3.5, 4, 4, 6, 0, 130))


def test_tiers_use_frozen_cutoffs():
    assert pm.tier(4.0, [], 6, PARAMS) == 'Lean'
    assert pm.tier(4.0, ['x'], 6, PARAMS) == 'Watch'
    assert pm.tier(4.0, [], 4, PARAMS) == 'Watch'
    assert pm.tier(0.5, [], 6, PARAMS) == 'Pass'


def test_frozen_versions_are_immutable(tmp_path):
    pm.save_version('v9', {k: v for k, v in PARAMS.items() if k != 'version'}, models_dir=tmp_path)
    assert pm.load_params('v9', tmp_path)['version'] == 'v9'
    with pytest.raises(SystemExit):
        pm.save_version('v9', PARAMS, models_dir=tmp_path)         # cannot overwrite
    p = tmp_path / 'v9' / 'params.json'
    edited = json.loads(p.read_text())
    edited['shrink'] = 0.9
    p.write_text(json.dumps(edited))
    with pytest.raises(RuntimeError):
        pm.load_params('v9', tmp_path)                              # tampering is detected


def test_active_model_is_frozen_and_loads():
    params = pm.load_params()   # raises if models/<active>/params.json no longer matches its recorded hash
    assert params['version'] == pm.ACTIVE_MODEL and params['oos_from_week'] >= 8


def synthetic_slate():
    books = ['DraftKings', 'FanDuel', 'BetMGM', 'Caesars', 'Fanatics', 'Hard Rock']
    lines, proj = [], []
    for i in range(14):
        name, base = f'Player {chr(65 + i)}', 30.5 + 3 * i
        for j, b in enumerate(books):
            ln = base + (1 if j == 0 else 0)   # DraftKings posts the softest-for-unders line
            lines += [dict(Week=8, Player=name, Pos='WR', Team='AAA', Opp='BBB', Stat='Rec Yds', Book=b, Side=s, Line=ln, Odds=-115)
                      for s in ('over', 'under')]
        proj.append(dict(Week=8, Player=name, Pos='WR', Team='AAA', Opp='BBB', pass_yds=0, rush_yds=0, rec_yds=base + 4, rec_catch=0))
    return pd.DataFrame(lines), pd.DataFrame(proj)


def test_score_slate_end_to_end_is_consistent():
    lines, proj = synthetic_slate()
    picks, unmatched = pv.score_slate(lines, proj, PARAMS, log=lambda *_: None)
    assert not unmatched
    assert set(picks['Model']) == {'original', 'market_only', 'vt'}
    act = picks[picks['Model'] == 'vt']
    assert len(act) == 14
    for r in act.itertuples():
        # EV recomputed from the printed probability and odds must match
        assert r.EV_Pct == pytest.approx(100 * pm.ev_per_unit(r.P_Win, r.Odds), abs=0.06)
        assert r.BreakEven == pytest.approx(pm.break_even(r.Odds), abs=1e-3)
        # the three probability steps explain the whole gap to break-even
        assert r.Mkt_Edge_Pts + r.Skew_Pts + r.Proj_Pts == pytest.approx(100 * (r.P_Win - r.BreakEven), abs=0.3)
    # deterministic: same inputs, same picks (so a replay equals what the live run produced)
    again, _ = pv.score_slate(lines, proj, PARAMS, log=lambda *_: None)
    pd.testing.assert_frame_equal(picks.drop(columns='_trace'), again.drop(columns='_trace'))


def test_explain_runs_and_matches_the_row():
    lines, proj = synthetic_slate()
    picks, _ = pv.score_slate(lines, proj, PARAMS, log=lambda *_: None)
    row = picks[picks['Model'] == 'vt'].iloc[0]
    text = pv.explain(row, PARAMS)
    assert row['Player'] in text and f"{row['EV_Pct']:+.1f}% per unit" in text and 'left out' in text
