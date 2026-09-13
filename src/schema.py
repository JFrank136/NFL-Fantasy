"""The shared row shapes every source's raw output gets normalized into.

Long format: one row per (season, week, source, scoring, player) pull. A
re-pull of the same key is a NEW row (distinguished by `pulled_at`), never an
overwrite -- storage.py enforces the append-only part, this module just
defines the columns.
"""

from dataclasses import dataclass, asdict, fields

LONG_FORMAT_COLUMNS = [
    "season", "week", "source", "scoring", "pulled_at",
    "source_player_id", "player_name", "canonical_name", "team", "position",
    "rank", "projection", "floor_proj", "ceiling_proj", "tier",
    "bye", "opponent",
]


@dataclass
class RankingRow:
    season: int
    week: int
    source: str          # "draftsharks" | "boone" | "smythe"
    scoring: str          # "half-ppr" | "ppr"
    pulled_at: str         # ISO 8601 timestamp, UTC
    source_player_id: str
    player_name: str
    canonical_name: str
    team: str | None
    position: str
    rank: int | None
    projection: float | None
    floor_proj: float | None = None
    ceiling_proj: float | None = None
    tier: int | None = None
    bye: int | None = None
    opponent: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in LONG_FORMAT_COLUMNS}


assert [f.name for f in fields(RankingRow)] == LONG_FORMAT_COLUMNS, (
    "RankingRow fields drifted from LONG_FORMAT_COLUMNS -- keep them in sync, "
    "storage.py's CSV header depends on this exact order"
)


TRADE_VALUE_COLUMNS = [
    "season", "week", "source", "position", "pulled_at", "source_url",
    "rank", "player_name", "canonical_name", "team", "value_col1_label",
    "value_col1", "value_col2_label", "value_col2",
]


@dataclass
class TradeValueRow:
    season: int
    week: int              # week this chart was published for
    source: str              # "boone" (room for another expert later)
    position: str
    pulled_at: str            # ISO 8601 timestamp, UTC
    source_url: str
    rank: int | None
    player_name: str
    canonical_name: str
    team: str | None          # not present in the source table -- always None today
    value_col1_label: str      # e.g. "HALF" (RB/WR/TE) or "1QB" (QB)
    value_col1: float | None
    value_col2_label: str      # e.g. "PPR" (RB/WR/TE) or "2QB" (QB)
    value_col2: float | None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in TRADE_VALUE_COLUMNS}


assert [f.name for f in fields(TradeValueRow)] == TRADE_VALUE_COLUMNS, (
    "TradeValueRow fields drifted from TRADE_VALUE_COLUMNS -- keep them in "
    "sync, storage.py's CSV header depends on this exact order"
)
