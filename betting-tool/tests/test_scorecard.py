import pandas as pd
import pytest

import prop_model
import prop_value as pv
import scorecard as sc
from tests.test_prop_model import PARAMS


def test_avg_american_odds():
    assert sc.avg_american([-110, -110]) == -110
    assert sc.avg_american([100, 100]) == 100
    assert sc.avg_american([-200, 200]) == 125   # decimals 1.5 and 3.0 average to 2.25


def test_weekly_top_is_lean_only_capped_and_never_padded():
    out = pd.DataFrame({'Player': [f'P{i}' for i in range(30)], 'Stat': 'Rec Yds', 'Pick': 'U 40.5', 'Book': 'DK',
                        'Tier': ['Lean'] * 25 + ['Watch'] * 5, 'EV_Pct': [30 - i for i in range(30)]})
    picks = pd.DataFrame({'Model': 'market_only', 'Player': ['P0', 'P1'], 'Stat': 'Rec Yds', 'Pick': ['U 40.5', 'O 40.5'], 'Book': 'DK'})
    top = pv.weekly_top(out, picks, PARAMS)
    assert len(top) == 20 and set(top['Tier']) == {'Lean'} and top['EV_Pct'].is_monotonic_decreasing
    assert list(top['Mkt_Agrees'][:2]) == [True, False] and not top['Mkt_Agrees'][2:].any()
    assert pv.weekly_top(out[out['Tier'] != 'Lean'], picks, PARAMS).empty   # nothing qualifies -> nothing forced


def test_head_to_head_ignores_identical_bets():
    def g(model, pick, units, result):
        return {'Week': 8, 'Player': 'A', 'Stat': 'Rec Yds', 'Model': model, 'Pick': pick, 'Book': 'DK', 'Odds': -110,
                'Result': result, 'Units': units, 'Sample': 'OUT-OF-SAMPLE'}
    graded = pd.DataFrame([g('v1', 'U 40.5', 0.91, 'win'), g('market_only', 'O 40.5', -1.0, 'loss')])
    h = sc.head_to_head(graded, 'v1')
    diff = h[h['Compared'] == 'different bets only'].iloc[0]
    assert diff['N'] == 1 and diff['units diff/bet'] == pytest.approx(1.91)


def test_frozen_code_check_reports_a_status():
    status = sc.frozen_code_status(prop_model.ACTIVE_MODEL)
    assert status.startswith(('OK', 'CHANGED', 'could not verify'))
