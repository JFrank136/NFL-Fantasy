import { useMemo, useState } from 'react'
import { useRosHistory } from '../lib/useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from '../lib/useBlendedRos'
import { buildMovers, describeBaseline, splitSnapshots, topMovers, TIMEFRAME_MIN_GAP_MS, type Metric, type MoverRow, type Timeframe } from '../lib/movers'

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

function MoversTable({ title, rows, kind }: { title: string; rows: MoverRow[]; kind: 'up' | 'down' }) {
  return (
    <div className="card p-4 space-y-2">
      <span className="label">{title}</span>
      <table className="table">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th className="text-right">Rank</th>
            <th className="text-right">Prev</th>
            <th className="text-right">Now</th>
            <th className="text-right">Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={`${r.canonicalName}::${r.position}`}>
              <td>{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
              <td>{r.position}</td>
              <td className="text-right">{r.rank ?? ''}</td>
              <td className="text-right">{fmt(r.previous)}</td>
              <td className="text-right font-semibold">{fmt(r.current)}</td>
              <td className={`text-right ${kind === 'up' ? 'signal-up' : 'signal-down'}`}>
                {(r.change as number) > 0 ? '+' : ''}{fmt(r.change)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <div className="subtle">No movement.</div>}
    </div>
  )
}

export default function MoversFallers() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [metric, setMetric] = useState<Metric>('blended')
  const [timeframe, setTimeframe] = useState<Timeframe>('latest')
  const [pos, setPos] = useState('ALL')
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)

  const result = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS[timeframe]
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    const movers = buildMovers(
      metric,
      { ds: ds.current.map(toDsRosInput), boone: boone.current.map(r => toBooneRosInput(r, scoring)) },
      {
        ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
        boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
      },
    )
    const sorted = (times: string[]) => [...times].sort((a, b) => Date.parse(a) - Date.parse(b))
    return {
      movers,
      currentDs: ds.current.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
      baselineDs: sorted(ds.baselineTimes),
      baselineBoone: sorted(boone.baselineTimes),
    }
  }, [dsRows, booneRows, scoring, metric, timeframe])

  const { risers, fallers } = useMemo(() => {
    const rows = pos === 'ALL' ? result.movers.rows : result.movers.rows.filter(r => r.position === pos)
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
        {!loading && !error && (
          <div className="subtle">
            {result.currentDs && `Current: ${new Date(result.currentDs).toLocaleString()} · `}
            {describeBaseline('Draft Sharks', result.baselineDs)} · {describeBaseline('Boone', result.baselineBoone)}
          </div>
        )}
        {loading && <div className="subtle">Loading history…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
      </div>

      {!loading && !error && !result.movers.baselineAvailable && (
        <div className="card p-4 subtle">
          Not enough history for this metric and timeframe yet — every source it needs must have a snapshot old enough to compare against.
        </div>
      )}

      {!loading && !error && result.movers.baselineAvailable && (
        <div className="grid md:grid-cols-2 gap-3">
          <MoversTable title="Risers" rows={risers} kind="up" />
          <MoversTable title="Fallers" rows={fallers} kind="down" />
        </div>
      )}
    </div>
  )
}
