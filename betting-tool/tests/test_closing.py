import json
from datetime import datetime, timedelta, timezone

import pytest

import closing
from props_lines import COLUMNS

NOW = datetime(2026, 11, 1, 16, 30, tzinfo=timezone.utc)


def row(player, start, line=40.5):
    return [8, player, 'WR', 'AAA', 'BBB', 'Rec Yds', 'DraftKings', 'over', line, -115, start.isoformat(), 1, 1]


def test_columns_match_row_shape():
    assert len(row('A', NOW)) == len(COLUMNS)


def test_idle_when_no_game_is_about_to_start(tmp_path):
    rows = [row('A', NOW + timedelta(hours=3)), row('B', NOW - timedelta(minutes=5))]  # later game, already started
    assert closing.capture(rows, NOW, 45, tmp_path) == (None, 'idle')
    assert not list(tmp_path.glob('*/meta.json'))


def test_saves_only_games_inside_the_window_then_dedupes(tmp_path):
    rows = [row('A', NOW + timedelta(minutes=20)), row('Zed', NOW + timedelta(hours=4))]
    dest, why = closing.capture(rows, NOW, 45, tmp_path)
    assert why == 'saved' and dest.name == '20261101T163000Z'
    assert 'Zed' not in (dest / 'prop_lines.csv').read_text()
    meta = json.loads((dest / 'meta.json').read_text())
    assert meta['quote_rows'] == 1 and meta['weeks'] == [8]
    assert closing.capture(rows, NOW + timedelta(minutes=5), 45, tmp_path) == (None, 'unchanged')   # same lines -> no new dir
    moved = [row('A', NOW + timedelta(minutes=20), line=41.5)]
    again, why = closing.capture(moved, NOW + timedelta(minutes=10), 45, tmp_path)
    assert why == 'saved' and again != dest                                                           # a line move IS kept


def test_record_logs_everything_but_idle(tmp_path):
    closing.record('idle', closing_dir=tmp_path, now=NOW)
    assert not (tmp_path / 'closing.log').exists()
    assert json.loads((tmp_path / 'last_run.json').read_text())['outcome'] == 'idle'
    closing.record('ERROR', 'ConnectionError: dns', closing_dir=tmp_path, now=NOW)
    assert 'ERROR' in (tmp_path / 'closing.log').read_text() and 'dns' in (tmp_path / 'closing.log').read_text()


def test_fetch_retries_then_raises():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError('no dns yet')
        return {'ok': True}

    assert closing.fetch_with_retry(flaky, attempts=3, wait=0) == {'ok': True} and len(calls) == 3

    def dead():
        raise ConnectionError('offline')

    with pytest.raises(ConnectionError):
        closing.fetch_with_retry(dead, attempts=2, wait=0)


def test_main_failure_is_logged_and_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(closing, 'CLOSING_DIR', tmp_path)
    monkeypatch.setattr(closing, 'fetch_with_retry', lambda: (_ for _ in ()).throw(ConnectionError('offline')))
    monkeypatch.setattr('sys.argv', ['closing.py'])
    real_record = closing.record
    monkeypatch.setattr(closing, 'record', lambda *a, **k: real_record(*a, closing_dir=tmp_path, **k))
    with pytest.raises(SystemExit) as e:
        closing.main()
    assert e.value.code == 1
    assert 'ERROR' in (tmp_path / 'closing.log').read_text()
