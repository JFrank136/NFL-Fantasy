"""
Operational health checks for forward testing, shown at the top of scorecard.py.

Answers four questions without changing anything: were all finished games/selections graded, did the closing-line
captures succeed or miss, were each week's predictions and sportsbook prices saved intact, and is any data stale,
missing or invalid. Each check returns (area, status, message) with status OK / WARN / FAIL. Only weeks at or after the
model's oos_from_week are held to the closing-capture and predictions-file requirements (earlier weeks predate them).
"""
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

PENDING_HOURS = 5        # grade.py treats a game as pending until this long after kickoff
CAPTURE_WINDOW = 60      # a game counts as captured if a closing capture exists within this many minutes before kickoff
PULL_DUE_HOURS = 36      # warn when a week kicks off within this long and has no snapshot yet
STALE_HOURS_GRADES = 12  # graded files should be refreshed within this long after the last finished game
SNAP_FILES = ['prop_lines.csv', 'ds_projections.csv', 'prop_value.csv']


def _names(df, n=6):
    items = [f"{r.Player} {r.Stat}" for r in df.drop_duplicates(['Player', 'Stat']).itertuples()]
    return ', '.join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else '')


def check_grading(graded, now, grades_dir):
    out = []
    done = graded[graded['Start'] + timedelta(hours=PENDING_HOURS) < now]
    live = len(graded) - len(done)
    counts = done['Result'].value_counts().to_dict()
    bad = done[done['Result'].isin(['pending', 'unverified'])]
    if bad.empty:
        out.append(('Grading', 'OK', f"all {len(done)} selections in finished games are graded {counts}; {live} still in unfinished games"))
    else:
        share = len(bad) / max(len(done), 1)
        out.append(('Grading', 'FAIL' if share > 0.02 else 'WARN',
                    f"{len(bad)} of {len(done)} finished selections not graded (no stats or snap-count evidence yet): {_names(bad)}"))
    if len(graded) and graded['Result'].isna().any():
        out.append(('Grading', 'FAIL', f"{int(graded['Result'].isna().sum())} selections have no result"))
    last_done = done['Start'].max() if len(done) else None
    for name, label in (('graded_picks.csv', 'pick grades'), ('universe.csv', 'all-lines universe')):
        f = Path(grades_dir) / name
        if not f.exists():
            out.append(('Grading', 'WARN', f"grades/{name} is missing (run grade.py / universe.py)"))
        elif last_done is not None and pd.Timestamp(f.stat().st_mtime, unit='s', tz='UTC') + timedelta(hours=STALE_HOURS_GRADES) < last_done + timedelta(hours=PENDING_HOURS):
            out.append(('Grading', 'WARN', f"{label} (grades/{name}) predates the latest finished game; run_all.py refreshes it, or run grade.py / universe.py"))
    return out


def check_closing(picks, now, closing_dir, oos_from_week):
    out = []
    closing_dir = Path(closing_dir)
    hb = closing_dir / 'last_run.json'
    if not hb.exists():
        out.append(('Closing', 'WARN', "no heartbeat file: the PropClosingLines task has not run (or closing/ was deleted)"))
    else:
        h = json.loads(hb.read_text())
        age = (now - pd.to_datetime(h['at_utc'], utc=True)).total_seconds() / 3600
        out.append(('Closing', 'WARN' if age > 24 else 'OK',
                    f"scheduler heartbeat {age:.1f}h ago ({h['outcome']})" + ("; STALE, check Get-ScheduledTaskInfo PropClosingLines" if age > 24 else '')))
    log = closing_dir / 'closing.log'
    errs = [ln for ln in log.read_text(encoding='utf-8').splitlines() if ' ERROR ' in ln] if log.exists() else []
    recent = [e for e in errs if pd.to_datetime(e.split()[0], utc=True) > now - timedelta(days=7)]
    out.append(('Closing', 'WARN' if recent else 'OK', f"{len(recent)} capture errors in the last 7 days" + (f"; latest: {recent[-1][:120]}" if recent else '')))
    caps = []
    for f in sorted(closing_dir.glob('*/meta.json')):
        c = pd.read_csv(f.parent / 'prop_lines.csv', usecols=['Start'])
        caps.append((pd.to_datetime(json.loads(f.read_text())['captured_at_utc'], utc=True), set(pd.to_datetime(c['Start'], utc=True))))
    starts = pd.to_datetime(picks['Start'], utc=True)
    games = starts[(picks['Week'] >= oos_from_week) & (starts < now)].drop_duplicates().sort_values()
    if games.empty:
        out.append(('Closing', 'OK', f"no kickoffs yet in out-of-sample weeks (>= {oos_from_week}); {len(caps)} captures so far"))
        return out
    missed = [s for s in games if not any(s - timedelta(minutes=CAPTURE_WINDOW) <= t < s and s in starts for t, starts in caps)]
    cov = f"{len(games) - len(missed)} of {len(games)} kickoff times have a capture in the {CAPTURE_WINDOW} min before"
    when = ', '.join(s.strftime('%a %m/%d %H:%MZ') for s in missed[:5])
    out.append(('Closing', 'OK' if not missed else ('FAIL' if len(missed) > len(games) / 2 else 'WARN'), cov + (f"; MISSED: {when}" if missed else '')))
    return out


def _digest(d):
    h = hashlib.sha256()
    for f in SNAP_FILES:
        h.update((d / f).read_bytes())
    return h.hexdigest()


def check_snapshots(snap_dir, params, now, expected_weeks=None, kickoffs=None):
    """Integrity of every live snapshot (prices + predictions), and a snapshot for every week already underway."""
    out, seen, first_cap = [], {}, {}
    version, oos = params['version'], params['oos_from_week']
    for mf in sorted(Path(snap_dir).glob('*/meta.json')):
        d, meta = mf.parent, json.loads(mf.read_text())
        if meta.get('provenance') == 'imported':
            continue
        week, problems = meta['week'], []
        missing = [f for f in SNAP_FILES if not (d / f).exists()]
        if missing:
            out.append(('Saved data', 'FAIL', f"{d.name} (week {week}) missing {', '.join(missing)}"))
            continue
        seen.setdefault(week, []).append(d.name)
        first_cap[week] = min(first_cap.get(week, pd.Timestamp.max.tz_localize('UTC')), pd.to_datetime(meta['captured_at_utc'], utc=True))
        if _digest(d) != meta['sha256']:
            problems.append('files changed since saved (hash mismatch)')
        lines, value = pd.read_csv(d / 'prop_lines.csv'), pd.read_csv(d / 'prop_value.csv')
        if len(lines) != meta['quote_rows'] or len(value) != meta['pick_rows']:
            problems.append('row counts differ from meta')
        if lines[['Line', 'Odds', 'Side', 'Book']].isna().any().any():
            problems.append('quotes with missing line/odds/side/book')
        if ((lines['Odds'].abs() < 100) | (lines['Line'] <= 0)).any():
            problems.append('invalid odds or non-positive lines')
        sides = lines.groupby(['Player', 'Stat', 'Book'])['Side'].nunique()
        if (sides < 2).mean() > 0.10:
            problems.append(f"{100 * (sides < 2).mean():.0f}% of player/stat/book quotes have only one side")
        if pd.to_datetime(meta['captured_at_utc'], utc=True) >= pd.to_datetime(lines['Start'], utc=True).min() + timedelta(hours=1):
            problems.append('captured after the first kickoff')
        if week >= oos:
            p = d / 'prop_predictions.csv'
            if not p.exists():
                problems.append('prop_predictions.csv missing (3-model predictions not saved)')
            else:
                pred = pd.read_csv(p)
                n = pred.groupby('Model').size()
                if set(n.index) != {'original', 'market_only', version} or n.nunique() != 1:
                    problems.append(f"predictions incomplete: {n.to_dict()}")
        out.append(('Saved data', 'FAIL' if problems else 'OK',
                    f"snapshot {d.name} (week {week}, {len(lines)} quotes, {len(value)} candidates): " + ('; '.join(problems) if problems else 'intact')))
    for w, cap in sorted(first_cap.items()):
        if w < oos:
            continue
        late = [k for k in (kickoffs or {}).get(w, []) if k < cap and k < now]
        if late:
            out.append(('Saved data', 'WARN', f"week {w}: {len(late)} kickoff time(s) passed before the first snapshot ({cap:%a %m/%d %H:%MZ}); "
                        f"those games have no pregame data and are EXCLUDED from evaluation: {', '.join(k.strftime('%a %m/%d %H:%MZ') for k in late)}"))
    for w in sorted(expected_weeks or []):
        if w >= oos and w not in seen:
            out.append(('Saved data', 'FAIL', f"week {w} has started but no snapshot (prices + predictions) was saved for it"))
    for w, ks in sorted((kickoffs or {}).items()):
        if w >= oos and w not in seen and now < ks[0] <= now + timedelta(hours=PULL_DUE_HOURS):
            out.append(('Saved data', 'WARN', f"week {w} kicks off {ks[0]:%a %m/%d %H:%MZ} and has no snapshot yet; the weekly pull is due "
                        f"(python weekly_pull.py)"))
    return out


def check_pull(log_file, now):
    """Failures of the unattended weekly pull (logs/weekly_pull.log)."""
    log_file = Path(log_file)
    if not log_file.exists():
        return [('Weekly pull', 'OK', "no pull log yet (the scheduled PropWeeklyPull task has not run)")]
    lines = [ln for ln in log_file.read_text(encoding='utf-8').splitlines() if ln.strip()]
    recent = [ln for ln in lines if pd.to_datetime(ln.split()[0], utc=True) > now - timedelta(days=7)]
    errs = [ln for ln in recent if ' ERROR ' in ln]
    oks = [ln for ln in lines if ' OK ' in ln]
    last = f"last success {oks[-1][:25]}" if oks else "no successful pull logged yet"
    if errs:
        return [('Weekly pull', 'WARN', f"{len(errs)} failed attempt(s) in the last 7 days; latest: {errs[-1][27:150]}; {last}")]
    return [('Weekly pull', 'OK', f"no failures in the last 7 days; {last}")]


def check_inputs(root, now, max_age_days=4):
    """Working files the next run will read: present, parseable, same week, not stale."""
    out, root = [], Path(root)
    try:
        lines, proj = pd.read_csv(root / 'data' / 'prop_lines.csv'), pd.read_csv(root / 'data' / 'ds_projections.csv')
    except (OSError, ValueError) as e:
        return [('Inputs', 'FAIL', f"cannot read data/prop_lines.csv or data/ds_projections.csv: {type(e).__name__}")]
    age = (now - pd.Timestamp((root / 'data' / 'prop_lines.csv').stat().st_mtime, unit='s', tz='UTC')).total_seconds() / 86400
    out.append(('Inputs', 'WARN' if age > max_age_days else 'OK', f"data/prop_lines.csv pulled {age:.1f} days ago (week {int(lines['Week'].iloc[0])}, {len(lines)} quotes)"
                + ("; STALE" if age > max_age_days else '')))
    if set(lines['Week']) != set(proj['Week']):
        out.append(('Inputs', 'WARN', f"prop_lines week {sorted(set(lines['Week']))} != projections week {sorted(set(proj['Week']))}"))
    if proj[['pass_yds', 'rush_yds', 'rec_yds', 'rec_catch']].isna().any().any():
        out.append(('Inputs', 'WARN', "projections contain missing values"))
    return out


def schedule_kickoffs(now, season=2026):
    """{week: sorted distinct kickoff times (UTC)} for the regular season from nflverse; {} if it cannot be loaded."""
    try:
        import nflreadpy
        sc = nflreadpy.load_schedules([season]).to_pandas()
        sc['ko'] = pd.to_datetime(sc['gameday'] + ' ' + sc['gametime']).dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
        reg = sc[sc['game_type'] == 'REG'].dropna(subset=['ko'])
        return {int(w): sorted(g['ko'].drop_duplicates()) for w, g in reg.groupby('week')}
    except Exception:
        return {}


def run_checks(graded, picks, params, now, root, snap_dir, closing_dir, grades_dir, weeks=None, pull_log=None):
    kickoffs = schedule_kickoffs(now) if weeks is None else {}
    weeks = [w for w, ks in kickoffs.items() if ks[0] < now] if weeks is None else weeks
    return (check_grading(graded, now, grades_dir) + check_closing(picks, now, closing_dir, params['oos_from_week'])
            + check_snapshots(snap_dir, params, now, weeks, kickoffs) + check_pull(pull_log or Path(root) / 'logs' / 'weekly_pull.log', now)
            + check_inputs(root, now))


def render(results):
    lines = [f"  [{s:<4}] {a:<10} {m}" for a, s, m in results]
    bad, warn = sum(s == 'FAIL' for _, s, _ in results), sum(s == 'WARN' for _, s, _ in results)
    head = "Operational health: all clear" if not (bad or warn) else f"Operational health: {bad} failure(s), {warn} warning(s)"
    return '\n'.join([head] + lines)
