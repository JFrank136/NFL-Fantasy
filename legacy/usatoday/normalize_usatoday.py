"""Archived from src/normalize.py when USA Today was retired. Needs `from src.normalize import TradeValueRow, canonical_name_for` (adjust to wherever those live) and `TradeValueTableRow` from usatoday_trade_values.py."""

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
