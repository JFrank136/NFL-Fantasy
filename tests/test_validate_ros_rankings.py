from src.schema import RosRankingRow
from src.validate import validate_ros_rankings


def make_row(player_name="Player", position="RB", rank=1, source_player_id="1", **kw):
    defaults = dict(
        season=2026, source="draftsharks", scoring="half-ppr",
        pulled_at="2026-09-16T00:00:00+00:00", as_of_week=3,
        source_player_id=source_player_id, player_name=player_name,
        canonical_name=player_name, team="DET", position=position, rank=rank,
        tier_overall=1, tier_positional=1, projection=200.0, floor_proj=150.0,
        ceiling_proj=250.0, ds_value=90.0, strength_of_schedule="-1.0%",
        games_played=14, injury_risk="5", bye=6,
    )
    defaults.update(kw)
    return RosRankingRow(**defaults)


def test_empty_pull_is_an_error():
    issues = validate_ros_rankings([])
    assert any(i.severity == "error" for i in issues)


def test_blank_player_name_is_an_error():
    rows = [make_row(player_name="")]
    issues = validate_ros_rankings(rows)
    assert any(i.severity == "error" for i in issues)


def test_blank_position_is_an_error():
    rows = [make_row(position="")]
    issues = validate_ros_rankings(rows)
    assert any(i.severity == "error" for i in issues)


def test_below_position_floor_is_a_warning_not_an_error():
    rows = [make_row(player_name=f"Player {i}", source_player_id=str(i)) for i in range(3)]
    issues = validate_ros_rankings(rows, position_floors={"RB": 30})
    assert any(i.severity == "warning" for i in issues)
    assert not any(i.severity == "error" for i in issues)


def test_healthy_pull_has_no_issues():
    rows = [
        make_row(player_name=f"Player {i}", source_player_id=str(i), rank=i)
        for i in range(35)
    ]
    issues = validate_ros_rankings(rows, position_floors={"RB": 30})
    assert issues == []
