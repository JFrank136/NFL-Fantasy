import json

from scripts.push_to_supabase import _coerce_row, _read_new_rows, _read_state, _write_state


def test_coerce_row_converts_int_and_float_columns_and_leaves_blanks_as_none():
    row = {"season": "2026", "week": "2", "rank": "", "projection": "12.5", "player_name": "X"}
    out = _coerce_row(row, int_cols={"season", "week", "rank"}, float_cols={"projection"})
    assert out == {"season": 2026, "week": 2, "rank": None, "projection": 12.5, "player_name": "X"}


def test_read_new_rows_skips_already_pushed_rows(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
    rows = _read_new_rows(csv_path, already_pushed=1)
    assert rows == [{"a": "3", "b": "4"}, {"a": "5", "b": "6"}]


def test_read_new_rows_returns_empty_list_for_missing_file(tmp_path):
    assert _read_new_rows(tmp_path / "missing.csv", already_pushed=0) == []


def test_state_roundtrip(tmp_path, monkeypatch):
    import scripts.push_to_supabase as mod
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", state_path)
    assert _read_state() == {"rankings_rows_pushed": 0, "trade_values_rows_pushed": 0}
    _write_state({"rankings_rows_pushed": 5, "trade_values_rows_pushed": 2})
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
    }
    assert _read_state() == {"rankings_rows_pushed": 5, "trade_values_rows_pushed": 2}
