from src.schema import RankingRow
from src.validate import (
    check_no_duplicate_players,
    check_not_identical_to_other_source,
    check_position_counts,
    check_required_fields,
    dedupe_players,
    has_errors,
    validate_pull,
)


def make_row(player_name="Player", position="RB", rank=1, source_player_id="1", **kw):
    defaults = dict(
        season=2026, week=1, source="draftsharks", scoring="half-ppr",
        pulled_at="2026-09-08T00:00:00+00:00", source_player_id=source_player_id,
        player_name=player_name, canonical_name=player_name, team="DET",
        position=position, rank=rank, projection=15.0,
    )
    defaults.update(kw)
    return RankingRow(**defaults)


def test_empty_pull_is_an_error():
    issues = validate_pull([])
    assert has_errors(issues)


def test_blank_player_name_is_an_error():
    rows = [make_row(player_name="")]
    issues = check_required_fields(rows)
    assert any(i.severity == "error" for i in issues)


def test_duplicate_player_is_an_error_via_the_safety_net_check():
    rows = [make_row(source_player_id="1"), make_row(source_player_id="1")]
    issues = check_no_duplicate_players(rows)
    assert len(issues) == 1
    assert issues[0].severity == "error"


def test_dedupe_players_drops_repeats_and_warns_instead_of_erroring():
    rows = [
        make_row(source_player_id="1", player_name="Geno Smith", rank=37),
        make_row(source_player_id="1", player_name="Geno Smith", rank=38),
        make_row(source_player_id="2", player_name="Someone Else"),
    ]
    deduped, issues = dedupe_players(rows)
    assert len(deduped) == 2
    assert deduped[0].rank == 37  # first occurrence kept
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "Geno Smith" in issues[0].message
    # and the safety-net check now sees clean data:
    assert check_no_duplicate_players(deduped) == []


def test_dedupe_players_is_a_noop_when_nothing_is_duplicated():
    rows = [make_row(source_player_id="1"), make_row(source_player_id="2")]
    deduped, issues = dedupe_players(rows)
    assert deduped == rows
    assert issues == []


def test_thin_position_group_is_a_warning_not_an_error():
    rows = [make_row(position="QB") for _ in range(3)]
    issues = check_position_counts(rows, floors={"QB": 20})
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert not has_errors(issues)


def test_healthy_pull_has_no_errors():
    rows = (
        [make_row(position="QB", source_player_id=f"qb{i}") for i in range(25)]
        + [make_row(position="RB", source_player_id=f"rb{i}") for i in range(35)]
        + [make_row(position="WR", source_player_id=f"wr{i}") for i in range(35)]
        + [make_row(position="TE", source_player_id=f"te{i}") for i in range(12)]
    )
    issues = validate_pull(rows)
    assert not has_errors(issues)


def test_identical_top_n_across_sources_is_flagged():
    boone = [make_row(position="RB", player_name=f"Player {i}", rank=i, source_player_id=f"{i}")
             for i in range(1, 11)]
    smythe = [make_row(position="RB", player_name=f"Player {i}", rank=i, source_player_id=f"{i}")
              for i in range(1, 11)]
    issues = check_not_identical_to_other_source(smythe, boone)
    assert len(issues) == 1
    assert issues[0].severity == "warning"


def test_genuinely_different_rankings_are_not_flagged():
    boone = [make_row(position="RB", player_name=f"Player {i}", rank=i, source_player_id=f"{i}")
             for i in range(1, 11)]
    smythe = [make_row(position="RB", player_name=f"Player {11 - i}", rank=i, source_player_id=f"{i}")
              for i in range(1, 11)]
    issues = check_not_identical_to_other_source(smythe, boone)
    assert issues == []
