from src.normalize import (
    boone_trade_values_to_rows,
    draftsharks_to_ranking_rows,
    yahoo_expert_to_ranking_rows,
)
from src.sources.boone_trade_values import TradeValueTableRow
from src.sources.draftsharks_weekly import DraftSharksRow
from src.sources.yahoo_weekly_consensus import ExpertWeeklyRow


def test_draftsharks_to_ranking_rows_resolves_canonical_name():
    raw = [DraftSharksRow(
        source_player_id="123", player_name="Cam Skattebo", team="NYG",
        position="RB", rank=5, matchup="@KC", strength_of_schedule="-1.0%",
        bye=9, floor_proj=8.0, consensus_proj=12.0, ds_proj=11.0,
        ceiling_proj=16.0, three_d_proj=12.5, tier_overall=1,
        tier_positional=1, is_rookie=False,
    )]
    rows = draftsharks_to_ranking_rows(
        raw, season=2026, week=2, scoring="half-ppr",
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Cameron Skattebo"


def test_yahoo_expert_to_ranking_rows_falls_back_to_normalized_name_when_no_alias():
    raw = [ExpertWeeklyRow(
        source_player_id="9", player_name="Some Rookie", team="DAL",
        position="WR", rank=40, bye=7, opponent="vs. PHI",
    )]
    rows = yahoo_expert_to_ranking_rows(
        raw, source="boone", season=2026, week=2, scoring="ppr",
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "some rookie"


def test_boone_trade_values_to_rows_resolves_canonical_name():
    raw = [TradeValueTableRow(
        rank=3, player_name="Kenny Gainwell", value_col1_label="HALF",
        value_col1=14.2, value_col2_label="PPR", value_col2=15.9,
    )]
    rows = boone_trade_values_to_rows(
        "RB", "https://example.com", raw, season=2026, week=2,
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Kenneth Gainwell"


from src.normalize import draftsharks_ros_to_rows
from src.sources.draftsharks_ros import DraftSharksRosRow


def test_draftsharks_ros_to_rows_resolves_canonical_name():
    raw = [DraftSharksRosRow(
        source_player_id="123", player_name="Cam Skattebo", team="NYG",
        position="RB", rank=5, tier_overall=1, tier_positional=1,
        strength_of_schedule="-1.0%", bye=9, games_played=14,
        floor_proj=150.0, projection=180.0, ceiling_proj=210.0,
        ds_value=88.0, injury_risk="5",
    )]
    rows = draftsharks_ros_to_rows(
        raw, season=2026, as_of_week=3, scoring="half-ppr",
        pulled_at="2026-09-16T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Cameron Skattebo"
    assert rows[0].source == "draftsharks"
    assert rows[0].as_of_week == 3
    assert rows[0].ds_value == 88.0
