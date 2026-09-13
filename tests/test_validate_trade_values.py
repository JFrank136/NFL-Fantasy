from src.schema import TradeValueRow
from src.validate import validate_trade_values


def make_row(player_name="Player", rank=1, **kw):
    defaults = dict(
        season=2026, week=1, source="boone", position="RB",
        pulled_at="2026-09-11T00:00:00+00:00",
        source_url="https://sports.yahoo.com/fantasy/article/x.html",
        rank=rank, player_name=player_name, canonical_name=player_name, team=None,
        value_col1_label="HALF", value_col1=50.0,
        value_col2_label="PPR", value_col2=55.0,
    )
    defaults.update(kw)
    return TradeValueRow(**defaults)


def test_empty_pull_is_an_error():
    issues = validate_trade_values([], position="RB")
    assert any(i.severity == "error" for i in issues)


def test_blank_player_name_is_an_error():
    rows = [make_row(player_name="")]
    issues = validate_trade_values(rows, position="RB")
    assert any(i.severity == "error" for i in issues)


def test_below_floor_is_a_warning_not_an_error():
    rows = [make_row(player_name=f"Player {i}") for i in range(3)]
    issues = validate_trade_values(rows, position="RB", floor=30)
    assert any(i.severity == "warning" for i in issues)
    assert not any(i.severity == "error" for i in issues)


def test_healthy_pull_has_no_issues():
    rows = [make_row(player_name=f"Player {i}", rank=i) for i in range(35)]
    issues = validate_trade_values(rows, position="RB", floor=30)
    assert issues == []
