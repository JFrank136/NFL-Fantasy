"""Maps each source's raw row shape into the one shared RankingRow schema."""

from src.schema import RankingRow, TradeValueRow
from src.sources.boone_trade_values import TradeValueTableRow
from src.sources.draftsharks_weekly import DraftSharksRow
from src.sources.yahoo_weekly_consensus import ExpertWeeklyRow


def draftsharks_to_ranking_rows(
    rows: list[DraftSharksRow], season: int, week: int, scoring: str, pulled_at: str
) -> list[RankingRow]:
    return [
        RankingRow(
            season=season, week=week, source="draftsharks", scoring=scoring,
            pulled_at=pulled_at, source_player_id=r.source_player_id,
            player_name=r.player_name, team=r.team, position=r.position,
            rank=r.rank, projection=r.three_d_proj, floor_proj=r.floor_proj,
            ceiling_proj=r.ceiling_proj, tier=r.tier_overall, bye=r.bye,
            opponent=r.matchup,
        )
        for r in rows
    ]


def yahoo_expert_to_ranking_rows(
    rows: list[ExpertWeeklyRow], source: str, season: int, week: int, scoring: str,
    pulled_at: str,
) -> list[RankingRow]:
    """`source` is "boone" or "smythe" -- Yahoo's fanPro endpoint doesn't
    return a per-expert numeric projection, only a rank, so `projection`
    stays None for these rows (unlike Draft Sharks, which does have one)."""
    return [
        RankingRow(
            season=season, week=week, source=source, scoring=scoring,
            pulled_at=pulled_at, source_player_id=r.source_player_id,
            player_name=r.player_name, team=r.team, position=r.position,
            rank=r.rank, projection=None, bye=r.bye, opponent=r.opponent,
        )
        for r in rows
    ]


def boone_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[TradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="boone", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, team=None,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]
