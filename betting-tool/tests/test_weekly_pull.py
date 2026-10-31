import json

import pandas as pd

import weekly_pull as wp


def seed(root, lines_week=8, proj_week=8):
    """A fake `run` that writes the files each script would, and a fake snapshot like snapshot.py's."""
    (root / 'data').mkdir(exist_ok=True)
    calls = []

    def run(script):
        calls.append(script)
        if script == 'props_lines.py':
            pd.DataFrame({'Week': [lines_week]}).to_csv(root / 'data' / 'prop_lines.csv', index=False)
        if script == 'ds_projections.py':
            pd.DataFrame({'Week': [proj_week]}).to_csv(root / 'data' / 'ds_projections.csv', index=False)
        if script == 'snapshot.py':
            d = root / 'snapshots' / f'2026110{len(calls)}T000000Z'
            d.mkdir(parents=True)
            (d / 'meta.json').write_text(json.dumps({'week': lines_week, 'captured_at_utc': '2026-11-04T15:00:00+00:00'}))
        return 0
    return run, calls


def test_successful_pull_runs_every_step_and_logs_ok(tmp_path):
    run, calls = seed(tmp_path)
    assert wp.pull(run=run, root=tmp_path, log_file=tmp_path / 'log.txt', network=lambda: True) == 0
    assert calls == ['props_lines.py', 'grade.py', 'universe.py', 'ds_projections.py', 'prop_value.py', 'snapshot.py']
    assert ' OK ' in (tmp_path / 'log.txt').read_text()


def test_backup_run_skips_when_the_week_already_has_a_snapshot(tmp_path):
    run, calls = seed(tmp_path)
    wp.pull(run=run, root=tmp_path, log_file=tmp_path / 'log.txt', network=lambda: True)
    calls.clear()
    assert wp.pull(if_missing=True, run=run, root=tmp_path, log_file=tmp_path / 'log.txt', network=lambda: True) == 0
    assert calls == ['props_lines.py'] and 'SKIP' in (tmp_path / 'log.txt').read_text()


def test_projections_for_another_week_block_the_snapshot(tmp_path):
    run, calls = seed(tmp_path, lines_week=8, proj_week=7)
    assert wp.pull(run=run, root=tmp_path, log_file=tmp_path / 'log.txt', network=lambda: True) == 1
    assert 'snapshot.py' not in calls and 'prop_value.py' not in calls
    assert 'ERROR' in (tmp_path / 'log.txt').read_text() and not list((tmp_path / 'snapshots').glob('*')) if (tmp_path / 'snapshots').exists() else True


def test_failures_are_logged_and_return_nonzero(tmp_path):
    log = tmp_path / 'log.txt'
    assert wp.pull(run=lambda s: 0, root=tmp_path, log_file=log, network=lambda: False) == 1 and 'no network' in log.read_text()
    run, _ = seed(tmp_path)
    assert wp.pull(run=lambda s: 1 if s == 'props_lines.py' else run(s), root=tmp_path, log_file=log, network=lambda: True) == 1
    assert 'props_lines.py failed' in log.read_text()


def test_history_refresh_failure_does_not_block_the_pull(tmp_path):
    run, calls = seed(tmp_path)
    assert wp.pull(run=lambda s: 1 if s in ('grade.py', 'universe.py') else run(s), root=tmp_path, log_file=tmp_path / 'log.txt', network=lambda: True) == 0
    assert (tmp_path / 'log.txt').read_text().count('WARN') == 2


def test_network_gate_retries_then_gives_up():
    n = []
    def flaky():
        n.append(1)
        if len(n) < 3:
            raise OSError('dns')
    assert wp.wait_for_network(resolve=flaky, sleep=lambda s: None, tries=5) is True and len(n) == 3
    def dead():
        raise OSError('dns')
    assert wp.wait_for_network(resolve=dead, sleep=lambda s: None, tries=3) is False
