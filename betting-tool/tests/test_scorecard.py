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


def test_finalize_is_one_filterable_table_sorted_lean_first():
    act = pd.DataFrame({'Week': 8, 'Player': ['A', 'B', 'C'], 'Pos': 'WR', 'Team': 'X', 'Opp': 'Y', 'Stat': 'Rec Yds',
                        'Pick': ['U 40.5', 'O 30.5', 'U 50.5'], 'Odds': -110, 'Book': 'DK', 'P_Win': .55, 'BreakEven': .52,
                        'EV_Pct': [2.0, 9.0, 5.0], 'Tier': ['Watch', 'Pass', 'Lean'], 'Source': 'Projection', 'Flags': '',
                        'Model': 'v1', 'DS_Proj': 1.0, '_trace': None})
    picks = pd.DataFrame({'Model': 'market_only', 'Player': ['A', 'B'], 'Stat': 'Rec Yds', 'Pick': ['U 40.5', 'U 30.5'], 'Book': 'DK'})
    out = pv.finalize(act, picks)
    assert list(out.columns[:len(pv.LEAD_COLS)]) == pv.LEAD_COLS and 'Model' not in out.columns and '_trace' not in out.columns
    assert list(out['Player']) == ['C', 'A', 'B']                      # Lean, Watch, Pass
    assert list(out['Direction']) == ['Under', 'Under', 'Over'] and list(out['Line']) == [50.5, 40.5, 30.5]
    assert dict(zip(out['Player'], out['Mkt_Agrees'])) == {'A': 'Yes', 'B': 'No', 'C': 'No'}   # C has no market-only row


def test_started_games_are_dropped_before_scoring():
    now = pd.Timestamp('2026-11-05T02:00:00Z')
    lines = pd.DataFrame({'Player': ['A', 'B'], 'Start': ['2026-11-05T01:15:00+00:00', '2026-11-08T18:00:00+00:00']})
    kept, n = pv.drop_started(lines, now)
    assert list(kept['Player']) == ['B'] and n == 1


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
