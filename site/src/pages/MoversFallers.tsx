import { useMemo, useState } from 'react'
import { useRosHistory } from '../lib/useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from '../lib/useBlendedRos'
import { buildMovers, describeBaseline, explainMissingBaseline, explainMissingWeekBaseline, metricSources, splitSnapshots, topMovers, weekSnapshot, TIMEFRAME_MIN_GAP_MS, type Metric, type MoverRow, type Timeframe } from '../lib/movers'
import { onlyWeek } from '../lib/freshness'
import { useCurrentWeek } from '../lib/useCurrentWeek'
import ColumnPicker, { toggleInSet } from '../components/ColumnPicker'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }
const METRICS: { id: Metric; label: string }[] = [
  { id: 'blended', label: 'Blended ROS' },
  { id: 'boone', label: 'Boone ROS' },
  { id: 'ds', label: 'Draft Sharks ROS' },
  { id: 'ceiling', label: 'DS Ceiling' },
]
const TIMEFRAMES: { id: Timeframe; label: string }[] = [
  { id: 'latest', label: 'Latest change' },
  { id: 'week', label: 'Since last week' },
]
const LIST_SIZE = 15
// Movement among deep-bench players is noise (a 377th-ranked WR jumping 20
// spots is still a 377th-ranked WR), so rank 250+ never makes the lists.
const MAX_RANK = 250

function ScoringToggle({ value, onChange }: { value: Scoring; onChange: (s: Scoring) => void }) {
  return (
    <div className="toggle-switch" role="tablist" aria-label="Scoring format">
      {SCORINGS.map(s => (
        <span
          key={s}
          role="tab"
          aria-selected={value === s}
          className={`toggle-switch-option ${value === s ? 'toggle-switch-option-active' : ''}`}
          onClick={() => onChange(s)}
        >
          {SCORING_LABELS[s]}
        </span>
      ))}
    </div>
  )
}

const fmt = (n: number | null) => (n == null ? '—' : Math.round(n * 10) / 10)

const MOVER_COLUMNS = [
  { key: 'pos', label: 'Pos' },
  { key: 'rank', label: 'Rank' },
  { key: 'prev', label: 'Prev' },
  { key: 'now', label: 'Now' },
  { key: 'change', label: 'Change' },
]

function MoversTable({ title, rows, kind, hidden }: { title: string; rows: MoverRow[]; kind: 'up' | 'down'; hidden: Set<string> }) {
  const show = (key: string) => !hidden.has(key)
  return (
    <div className="card p-3 sm:p-4 space-y-2">
      <span className="label">{title}</span>
      <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th className="sticky-col">Player</th>
            {show('pos') && <th>Pos</th>}
            {show('rank') && <th className="text-right">Rank</th>}
            {show('prev') && <th className="text-right">Prev</th>}
            {show('now') && <th className="text-right">Now</th>}
            {show('change') && <th className="text-right">Change</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={`${r.canonicalName}::${r.position}`}>
              <td className="sticky-col">{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
              {show('pos') && <td>{r.position}</td>}
              {show('rank') && <td className="text-right">{r.rank ?? ''}</td>}
              {show('prev') && <td className="text-right">{fmt(r.previous)}</td>}
              {show('now') && <td className="text-right font-semibold">{fmt(r.current)}</td>}
              {show('change') && (
                <td className={`text-right ${kind === 'up' ? 'signal-up' : 'signal-down'}`}>
                  {(r.change as number) > 0 ? '+' : ''}{fmt(r.change)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {rows.length === 0 && <div className="subtle">No movement.</div>}
    </div>
  )
}

export default function MoversFallers() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [metric, setMetric] = useState<Metric>('blended')
  const [timeframe, setTimeframe] = useState<Timeframe>('latest')
  const [pos, setPos] = useState('ALL')
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set())
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)
  const { week: currentWeek } = useCurrentWeek()

  const previousWeek = currentWeek != null ? currentWeek - 1 : null

  const result = useMemo(() => {
    // "Current" is always each source's newest pull per position -- gap-
    // independent, so any minGapMs works here (it only affects baseline).
    const ds = splitSnapshots(dsRows, TIMEFRAME_MIN_GAP_MS.latest)
    const boone = splitSnapshots(booneRows, TIMEFRAME_MIN_GAP_MS.latest)
    // A source's own newest pull can still be a stale week if it hasn't
    // refreshed since the NFL week turned over -- gate "current" to this
    // week's data so a lagging source drops out instead of blending in.
    const dsCurrentRows = onlyWeek(ds.current, currentWeek, r => r.as_of_week)
    const booneCurrentRows = onlyWeek(boone.current, currentWeek, r => r.week)
    const boonePending = currentWeek != null && boone.current.length > 0 && booneCurrentRows.length === 0

    // "Latest change" is the most recent pull old enough by wall-clock time
    // (splitSnapshots' minGapMs cutoff); "Since last week" is specifically
    // the most recent pull actually tagged with the PREVIOUS NFL week, not
    // just "old enough" -- a fixed multi-day cutoff either fires too early
    // (mid-week reruns) or, as reported, sits unavailable for days after a
    // source's history genuinely already covers last week.
    const dsBase = timeframe === 'week'
      ? weekSnapshot(dsRows, previousWeek, r => r.as_of_week)
      : { rows: ds.baseline, times: ds.baselineTimes }
    const booneBase = timeframe === 'week'
      ? weekSnapshot(booneRows, previousWeek, r => r.week)
      : { rows: boone.baseline, times: boone.baselineTimes }

    const movers = buildMovers(
      metric,
      { ds: dsCurrentRows.map(toDsRosInput), boone: booneCurrentRows.map(r => toBooneRosInput(r, scoring)) },
      {
        ds: dsBase.rows.length ? dsBase.rows.map(toDsRosInput) : null,
        // A pending Boone has nothing in "current" at all, so comparing it
        // against a real week-old Boone baseline would misattribute
        // Boone's absence (not real movement) as a change.
        boone: !boonePending && booneBase.rows.length ? booneBase.rows.map(r => toBooneRosInput(r, scoring)) : null,
      },
    )
    const sorted = (times: string[]) => [...times].sort((a, b) => Date.parse(a) - Date.parse(b))
    return {
      movers,
      currentDs: dsCurrentRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
      baselineDs: sorted(dsBase.times),
      baselineBoone: sorted(booneBase.times),
      boonePending,
    }
  }, [dsRows, booneRows, scoring, metric, timeframe, currentWeek, previousWeek])

  const { risers, fallers } = useMemo(() => {
    const inRange = result.movers.rows.filter(r => r.rank != null && r.rank < MAX_RANK)
    const rows = pos === 'ALL' ? inRange : inRange.filter(r => r.position === pos)
    return topMovers(rows, LIST_SIZE)
  }, [result, pos])

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-1 flex-wrap">
            {METRICS.map(m => (
              <button key={m.id} className={`btn ${metric === m.id ? 'btn-primary' : ''}`} onClick={() => setMetric(m.id)}>{m.label}</button>
            ))}
          </div>
          <ScoringToggle value={scoring} onChange={setScoring} />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-1">
            {TIMEFRAMES.map(t => (
              <button key={t.id} className={`btn ${timeframe === t.id ? 'btn-primary' : ''}`} onClick={() => setTimeframe(t.id)}>{t.label}</button>
            ))}
          </div>
          <div className="flex gap-1">
            {POSITIONS.map(p => (
              <button key={p} className={`btn ${pos === p ? 'btn-primary' : ''}`} onClick={() => setPos(p)}>{p}</button>
            ))}
          </div>
        </div>
        <ColumnPicker columns={MOVER_COLUMNS} hidden={hiddenCols} onToggle={key => setHiddenCols(prev => toggleInSet(prev, key))} />
        {!loading && !error && (
          <div className="subtle">
            {result.currentDs && `Current: ${new Date(result.currentDs).toLocaleString()} · `}
            {describeBaseline('Draft Sharks', result.baselineDs)} · {describeBaseline('Boone', result.baselineBoone)} · Players ranked {MAX_RANK}+ are hidden
          </div>
        )}
        {!loading && !error && result.boonePending && (
          <div className="subtle">Boone hasn't updated ROS values for Week {currentWeek} yet -- excluded from "Current" until it does.</div>
        )}
        {loading && <div className="subtle">Loading history…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
      </div>

      {!loading && !error && !result.movers.baselineAvailable && (
        <div className="card p-4 space-y-1">
          <div className="subtle">Not enough history for this metric and timeframe yet:</div>
          {metricSources(metric).includes('ds') && !result.baselineDs.length && (
            <div className="subtle">
              {timeframe === 'week'
                ? explainMissingWeekBaseline('Draft Sharks', previousWeek)
                : explainMissingBaseline('Draft Sharks', dsRows, TIMEFRAME_MIN_GAP_MS.latest)}
            </div>
          )}
          {metricSources(metric).includes('boone') && (result.boonePending || !result.baselineBoone.length) && (
            <div className="subtle">
              {result.boonePending
                ? `Boone hasn't updated ROS values for Week ${currentWeek} yet, so there's nothing current to compare.`
                : timeframe === 'week'
                  ? explainMissingWeekBaseline('Boone', previousWeek)
                  : explainMissingBaseline('Boone', booneRows, TIMEFRAME_MIN_GAP_MS.latest)}
            </div>
          )}
        </div>
      )}

      {!loading && !error && result.movers.baselineAvailable && (
        <div className="grid md:grid-cols-2 gap-3">
          <MoversTable title="Risers" rows={risers} kind="up" hidden={hiddenCols} />
          <MoversTable title="Fallers" rows={fallers} kind="down" hidden={hiddenCols} />
        </div>
      )}
    </div>
  )
}
