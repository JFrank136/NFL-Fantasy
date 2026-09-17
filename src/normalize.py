"""Maps each source's raw row shape into the one shared RankingRow schema."""

from src.player_identity import canonical_name_for
from src.schema import RankingRow, RosRankingRow, TradeValueRow
from src.sources.boone_trade_values import TradeValueTableRow
from src.sources.cbs_trade_values import TradeValueTableRow as CbsTradeValueTableRow
from src.sources.draftsharks_ros import DraftSharksRosRow
from src.sources.draftsharks_weekly import DraftSharksRow
from src.sources.fantasypros_trade_values import (
    TradeValueTableRow as FantasyProsTradeValueTableRow,
)
from src.sources.rsj_trade_values import TradeValueTableRow as RsjTradeValueTableRow
from src.sources.usatoday_trade_values import (
    TradeValueTableRow as UsaTodayTradeValueTableRow,
)
from src.sources.yahoo_weekly_consensus import ExpertWeeklyRow


def draftsharks_to_ranking_rows(
    rows: list[DraftSharksRow], season: int, week: int, scoring: str, pulled_at: str
) -> list[RankingRow]:
    return [
        RankingRow(
            season=season, week=week, source="draftsharks", scoring=scoring,
            pulled_at=pulled_at, source_player_id=r.source_player_id,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
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
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
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
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=None,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]


def cbs_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[CbsTradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="cbs", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]


def fantasypros_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[FantasyProsTradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="fantasypros", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]


def rsj_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[RsjTradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="rsj", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]


def usatoday_trade_values_to_rows(
    position: str, source_path: str, table_rows: list[UsaTodayTradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="usatoday", position=position,
            pulled_at=pulled_at, source_url=source_path, rank=r.rank,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=None,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]


def draftsharks_ros_to_rows(
    rows: list[DraftSharksRosRow], season: int, as_of_week: int, scoring: str, pulled_at: str,
) -> list[RosRankingRow]:
    return [
        RosRankingRow(
            season=season, source="draftsharks", scoring=scoring,
            pulled_at=pulled_at, as_of_week=as_of_week,
            source_player_id=r.source_player_id, player_name=r.player_name,
            canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
            rank=r.rank, tier_overall=r.tier_overall, tier_positional=r.tier_positional,
            projection=r.projection, floor_proj=r.floor_proj, ceiling_proj=r.ceiling_proj,
            ds_value=r.ds_value, strength_of_schedule=r.strength_of_schedule,
            games_played=r.games_played, injury_risk=r.injury_risk, bye=r.bye,
        )
        for r in rows
    ]
