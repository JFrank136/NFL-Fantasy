import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

import health
from tests.test_prop_model import PARAMS

NOW = pd.Timestamp(datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc))


def graded(results, start=NOW - timedelta(days=2)):
    return pd.DataFrame({'Player': [f'P{i}' for i in range(len(results))], 'Stat': 'Rec Yds', 'Start': start, 'Result': results})


def status(rows, area=None):
    return [s for a, s, _ in rows if area in (None, a)]


def test_grading_ok_and_flags_ungraded_finished_games(tmp_path):
    for name in ('graded_picks.csv', 'universe.csv'):
        (tmp_path / name).write_text('x')
        os.utime(tmp_path / name, (NOW.timestamp(), NOW.timestamp()))
    ok = health.check_grading(graded(['win', 'loss', 'void']), NOW, tmp_path)
    assert status(ok) == ['OK']
    bad = health.check_grading(graded(['win'] * 3 + ['unverified']), NOW, tmp_path)
    assert 'FAIL' in status(bad) and 'P3 Rec Yds' in bad[0][2]
    live = health.check_grading(graded(['pending'], start=NOW + timedelta(hours=3)), NOW, tmp_path)   # game not over yet: fine
    assert status(live) == ['OK'] and '1 still in unfinished' in live[0][2]


def test_grading_warns_when_grade_files_missing(tmp_path):
    assert 'WARN' in status(health.check_grading(graded(['win']), NOW, tmp_path))


def make_capture(root, at, kickoff):
    d = root / at.strftime('%Y%m%dT%H%M%SZ')
    d.mkdir(parents=True)
    pd.DataFrame({'Start': [kickoff.isoformat()]}).to_csv(d / 'prop_lines.csv', index=False)
    (d / 'meta.json').write_text(json.dumps({'captured_at_utc': at.isoformat()}))


def test_closing_detects_missed_and_captured_kickoffs(tmp_path):
    k1, k2 = NOW - timedelta(days=1, hours=3), NOW - timedelta(days=1)
    picks = pd.DataFrame({'Week': 8, 'Start': [k1, k2]})
    make_capture(tmp_path, k1.to_pydatetime() - timedelta(minutes=20), k1)         # captured; k2 missed
    (tmp_path / 'last_run.json').write_text(json.dumps({'at_utc': (NOW - timedelta(hours=1)).isoformat(), 'outcome': 'idle'}))
    (tmp_path / 'closing.log').write_text(f"{(NOW - timedelta(days=1)).isoformat()}  ERROR     ConnectionError: dns\n")
    res = health.check_closing(picks, NOW, tmp_path, 8)
    closing = ' | '.join(m for _, _, m in res)
    assert '1 of 2 kickoff times' in closing and 'MISSED' in closing and '1 capture errors' in closing
    assert 'WARN' in status(res)


def test_closing_flags_a_dead_scheduler(tmp_path):
    (tmp_path / 'last_run.json').write_text(json.dumps({'at_utc': (NOW - timedelta(days=3)).isoformat(), 'outcome': 'idle'}))
    res = health.check_closing(pd.DataFrame({'Week': [], 'Start': []}), NOW, tmp_path, 8)
    assert 'WARN' in status(res) and 'STALE' in res[0][2]


def make_snapshot(root, week=8, predictions=True, tamper=False, models=('original', 'market_only', 'vt')):
    d = root / '20261108T000000Z'
    d.mkdir(parents=True)
    pd.DataFrame({'Week': week, 'Player': 'A', 'Stat': 'Rec Yds', 'Book': ['DK', 'DK', 'FD', 'FD'], 'Side': ['over', 'under'] * 2,
                  'Line': 40.5, 'Odds': -115, 'Start': '2026-11-08T18:00:00+00:00'}).to_csv(d / 'prop_lines.csv', index=False)
    pd.DataFrame({'Week': [week], 'Player': ['A'], 'pass_yds': 0, 'rush_yds': 0, 'rec_yds': 41.0, 'rec_catch': 3.0}).to_csv(d / 'ds_projections.csv', index=False)
    pd.DataFrame({'Week': [week], 'Player': ['A'], 'Pick': ['U 40.5']}).to_csv(d / 'prop_value.csv', index=False)
    if predictions:
        pd.DataFrame({'Model': list(models), 'Player': 'A'}).to_csv(d / 'prop_predictions.csv', index=False)
    (d / 'meta.json').write_text(json.dumps({'captured_at_utc': '2026-11-07T15:00:00+00:00', 'week': week, 'quote_rows': 4,
                                             'pick_rows': 1, 'sha256': health._digest(d)}))
    if tamper:
        (d / 'prop_value.csv').write_text('Week,Player,Pick\n8,A,O 40.5\n')
    return d


def test_snapshot_ok_tampered_and_missing_predictions(tmp_path):
    make_snapshot(tmp_path / 'a')
    assert status(health.check_snapshots(tmp_path / 'a', PARAMS, NOW, [8])) == ['OK']
    make_snapshot(tmp_path / 'b', tamper=True)
    assert 'hash mismatch' in health.check_snapshots(tmp_path / 'b', PARAMS, NOW, [8])[0][2]
    make_snapshot(tmp_path / 'c', predictions=False)
    assert 'prop_predictions.csv missing' in health.check_snapshots(tmp_path / 'c', PARAMS, NOW, [8])[0][2]
    make_snapshot(tmp_path / 'd', models=('original', 'vt'))
    assert 'predictions incomplete' in health.check_snapshots(tmp_path / 'd', PARAMS, NOW, [8])[0][2]


def test_missing_week_snapshot_is_a_failure_but_old_weeks_are_not(tmp_path):
    make_snapshot(tmp_path / 'a')
    res = health.check_snapshots(tmp_path / 'a', PARAMS, NOW, [7, 8, 9])
    assert [m for _, s, m in res if s == 'FAIL'] == ["week 9 has started but no snapshot (prices + predictions) was saved for it"]


def test_inputs_staleness_and_week_mismatch(tmp_path):
    (tmp_path / 'data').mkdir()
    pd.DataFrame({'Week': [8], 'Line': [1]}).to_csv(tmp_path / 'data' / 'prop_lines.csv', index=False)
    pd.DataFrame({'Week': [9], 'pass_yds': 1, 'rush_yds': 1, 'rec_yds': 1, 'rec_catch': 1}).to_csv(tmp_path / 'data' / 'ds_projections.csv', index=False)
    now = pd.Timestamp.now(tz='UTC')
    res = health.check_inputs(tmp_path, now + timedelta(days=6))
    assert status(res) == ['WARN', 'WARN'] and 'STALE' in res[0][2] and '!=' in res[1][2]
    assert health.check_inputs(tmp_path / 'nowhere', now)[0][1] == 'FAIL'


def test_render_summarises():
    assert health.render([('A', 'OK', 'fine')]).startswith('Operational health: all clear')
    assert '1 failure(s), 1 warning(s)' in health.render([('A', 'FAIL', 'x'), ('B', 'WARN', 'y')])


def test_games_that_kicked_off_before_the_first_snapshot_are_flagged(tmp_path):
    make_snapshot(tmp_path)   # captured 2026-11-07 15:00Z
    early = pd.Timestamp('2026-11-05T01:15:00Z')       # Thursday game, before the snapshot
    later = pd.Timestamp('2026-11-08T18:00:00Z')
    res = health.check_snapshots(tmp_path, PARAMS, NOW, [8], {8: [early, later]})
    warn = [m for _, s, m in res if s == 'WARN']
    assert len(warn) == 1 and '1 kickoff time(s) passed before the first snapshot' in warn[0] and 'Thu 11/05' in warn[0]
    assert not [m for _, s, m in health.check_snapshots(tmp_path, PARAMS, NOW, [8], {8: [later]}) if s == 'WARN']


def test_pull_log_failures_and_due_pull(tmp_path):
    log = tmp_path / 'weekly_pull.log'
    assert health.check_pull(log, NOW)[0][1] == 'OK'
    recent = (NOW - timedelta(days=1)).isoformat(timespec='seconds')
    log.write_text(f"{recent}  ERROR    projections are for week(s) [7] but lines are week 8; not snapshotting\n")
    res = health.check_pull(log, NOW)
    assert res[0][1] == 'WARN' and 'week(s) [7]' in res[0][2] and 'no successful pull' in res[0][2]
    log.write_text(log.read_text() + f"{NOW.isoformat(timespec='seconds')}  OK       week 8 pulled\n")
    assert 'last success' in health.check_pull(log, NOW)[0][2]
    make_snapshot(tmp_path / 'snaps')
    soon, far = NOW + timedelta(hours=20), NOW + timedelta(hours=100)
    res = health.check_snapshots(tmp_path / 'snaps', PARAMS, NOW, [8], {8: [NOW - timedelta(days=9)], 9: [soon], 10: [far]})
    due = [m for _, s, m in res if s == 'WARN' and 'pull is due' in m]
    assert len(due) == 1 and 'week 9' in due[0]
