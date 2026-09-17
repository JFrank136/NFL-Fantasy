import json

import requests

import scripts.push_to_supabase as mod
from scripts.push_to_supabase import (
    _coerce_row,
    _push_new_rows,
    _read_new_rows,
    _read_state,
    _write_state,
)


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
    assert _read_state() == {
        "rankings_rows_pushed": 0, "trade_values_rows_pushed": 0,
        "ros_rankings_rows_pushed": 0,
    }
    _write_state({
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    })
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    }
    assert _read_state() == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    }


def _write_csv(path, n_rows):
    lines = ["a,b"] + [f"{i},{i * 10}" for i in range(n_rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_push_new_rows_writes_state_after_each_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CHUNK", 2)
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", tmp_path / "state.json")

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, 5)

    insert_calls = []

    def fake_insert(table, rows, base_url, headers):
        insert_calls.append(rows)

    monkeypatch.setattr(mod, "_insert", fake_insert)

    state = {"rankings_rows_pushed": 0}
    result = _push_new_rows(
        csv_path, "in_season_rankings", set(), set(),
        state, "rankings_rows_pushed", "https://example.test", {},
    )

    assert result is True
    assert state["rankings_rows_pushed"] == 5
    assert len(insert_calls) == 3
    assert [len(c) for c in insert_calls] == [2, 2, 1]


def test_push_new_rows_persists_partial_progress_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CHUNK", 2)
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", tmp_path / "state.json")

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, 5)

    call_count = {"n": 0}

    def fake_insert(table, rows, base_url, headers):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise requests.RequestException("boom")

    monkeypatch.setattr(mod, "_insert", fake_insert)

    state = {"rankings_rows_pushed": 0}
    result = _push_new_rows(
        csv_path, "in_season_rankings", set(), set(),
        state, "rankings_rows_pushed", "https://example.test", {},
    )

    assert result is False
    assert state["rankings_rows_pushed"] == 2
    assert call_count["n"] == 2


def test_push_new_rows_returns_true_and_does_nothing_when_no_new_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", tmp_path / "state.json")

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, 5)

    insert_calls = []
    monkeypatch.setattr(
        mod, "_insert", lambda table, rows, base_url, headers: insert_calls.append(rows)
    )

    state = {"rankings_rows_pushed": 5}
    result = _push_new_rows(
        csv_path, "in_season_rankings", set(), set(),
        state, "rankings_rows_pushed", "https://example.test", {},
    )

    assert result is True
    assert insert_calls == []


def test_push_new_rows_detects_watermark_exceeding_csv_length(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", tmp_path / "state.json")

    csv_path = tmp_path / "rows.csv"
    _write_csv(csv_path, 5)

    insert_calls = []
    monkeypatch.setattr(
        mod, "_insert", lambda table, rows, base_url, headers: insert_calls.append(rows)
    )

    state = {"rankings_rows_pushed": 999}
    result = _push_new_rows(
        csv_path, "in_season_rankings", set(), set(),
        state, "rankings_rows_pushed", "https://example.test", {},
    )

    assert result is False
    assert insert_calls == []
