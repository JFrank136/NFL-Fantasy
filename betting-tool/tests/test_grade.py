import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

import grade


@pytest.mark.parametrize("d,line,actual,exp", [
    ('O', 50.5, 51, 'win'), ('O', 50.5, 50, 'loss'), ('U', 50.5, 50, 'win'), ('U', 50.5, 51, 'loss'),
    ('O', 50, 50, 'push'), ('U', 50, 50, 'push'), ('O', 50, 0, 'loss'), ('U', 50, 0, 'win'),
])
def test_settle(d, line, actual, exp):
    assert grade.settle(d, line, actual) == exp


def test_profit_units():
    assert grade.profit_units('win', -110) == pytest.approx(100 / 110)
    assert grade.profit_units('win', 150) == pytest.approx(1.5)
    assert grade.profit_units('loss', -250) == -1.0
    for r in ('push', 'void', 'pending', 'unverified'):
        assert grade.profit_units(r, -110) == 0.0


def test_break_even():
    assert grade.break_even(-110) == pytest.approx(110 / 210)
    assert grade.break_even(100) == pytest.approx(0.5)
    assert grade.break_even(200) == pytest.approx(1 / 3)


def test_wilson():
    lo, hi = grade.wilson(5, 10)
    assert lo < 0.5 < hi
    assert math.isnan(grade.wilson(0, 0)[0])
    assert grade.wilson(10, 10)[1] == pytest.approx(1.0)


def test_season_of():
    assert grade.season_of(pd.Timestamp('2026-10-18', tz='UTC')) == 2026
    assert grade.season_of(pd.Timestamp('2027-01-03', tz='UTC')) == 2026


def _pick(**kw):
    base = dict(Week=6, Player='Jayden Daniels', Pos='QB', Team='WAS', Stat='Pass Yds', Pick='O 200.5', Odds=-115,
                DS_Proj=230.2, Fair_Line=223.2, Start=pd.Timestamp('2026-10-18T13:00:00Z'))
    return {**base, **kw}


def _actuals(yards=250, name='Jayden Daniels'):
    return pd.DataFrame([dict(season=2026, week=6, key=grade.norm_name(name), TeamN='WSH', passing_yards=yards,
                              rushing_yards=0, receiving_yards=0)])


NOW = pd.Timestamp('2026-10-21', tz='UTC').to_pydatetime()


def test_grade_win_and_resid():
    g = grade.grade(pd.DataFrame([_pick()]), _actuals(250), now=NOW).iloc[0]
    assert g.Result == 'win' and g.Units == pytest.approx(100 / 115) and g.Resid_DS == pytest.approx(19.8)


def test_grade_under_loss():
    g = grade.grade(pd.DataFrame([_pick(Pick='U 200.5')]), _actuals(250), now=NOW).iloc[0]
    assert g.Result == 'loss' and g.Units == -1.0


def test_missing_actual_is_unverified_not_loss():
    g = grade.grade(pd.DataFrame([_pick()]), _actuals(name='Someone Else'), now=NOW).iloc[0]
    assert g.Result == 'unverified' and g.Units == 0.0 and pd.isna(g.Actual)


def test_recent_game_is_pending():
    now = pd.Timestamp('2026-10-18T14:00:00Z').to_pydatetime()
    g = grade.grade(pd.DataFrame([_pick()]), _actuals(name='Someone Else'), now=now).iloc[0]
    assert g.Result == 'pending'


def test_zero_yards_is_real_zero_when_row_exists():
    g = grade.grade(pd.DataFrame([_pick(Pick='U 200.5')]), _actuals(0), now=NOW).iloc[0]
    assert g.Result == 'win' and g.Actual == 0


def _snaps(name='Jayden Daniels', snaps=60.0):
    return pd.DataFrame([dict(season=2026, week=6, key=grade.norm_name(name), TeamN='WSH', snaps=snaps)])


def test_played_without_stats_row_is_zero():
    g = grade.grade(pd.DataFrame([_pick(Stat='Rush Yds', Pick='O 51.5')]), _actuals(name='X'), _snaps(), now=NOW).iloc[0]
    assert g.Result == 'loss' and g.Actual == 0 and g.Basis == 'snap_count_zero'


def test_no_snaps_but_team_published_is_void():
    snaps = _snaps(name='Teammate')
    snaps.loc[0, 'week'] = 6
    g = grade.grade(pd.DataFrame([_pick()]), _actuals(name='X'), snaps, now=NOW).iloc[0]
    assert g.Result == 'void' and g.Units == 0.0 and g.Basis == 'snap_count_dnp'


def test_no_snap_data_for_team_stays_unverified():
    g = grade.grade(pd.DataFrame([_pick()]), _actuals(name='X'), _snaps().iloc[0:0], now=NOW).iloc[0]
    assert g.Result == 'unverified'
