import { useMemo, useState } from 'react'
import { useRosHistory } from '../lib/useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from '../lib/useBlendedRos'
import { blendRosValues } from '../lib/blend'
import { buildMovers, describeBaseline, splitSnapshots, TIMEFRAME_MIN_GAP_MS, type Timeframe } from '../lib/movers'
import { currentDisagreements, directionDisagreements } from '../lib/disagreement'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }
const TIMEFRAMES: { id: Timeframe; label: string }[] = [
  { id: 'latest', label: 'Latest change' },
  { id: 'week', label: 'Since last week' },
]
const LIST_SIZE = 25

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

const r1 = (n: number) => Math.round(n * 10) / 10
const signed = (n: number) => `${n > 0 ? '+' : ''}${r1(n)}`
const signClass = (n: number) => (n > 0 ? 'signal-up' : n < 0 ? 'signal-down' : '')

export default function ExpertDisagreement() {
  const [view, setView] = useState<'current' | 'direction'>('current')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [timeframe, setTimeframe] = useState<Timeframe>('latest')
  const [pos, setPos] = useState('ALL')
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)

  const data = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS[timeframe]
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    const current = { ds: ds.current.map(toDsRosInput), boone: boone.current.map(r => toBooneRosInput(r, scoring)) }
    const baseline = {
      ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
      boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
    }

    const dsMovers = buildMovers('ds', current, baseline)
    const booneMovers = buildMovers('booneScaled', current, baseline)
    return {
      currentRows: currentDisagreements(blendRosValues(current.ds, current.boone)),
      directionRows: directionDisagreements(dsMovers.rows, booneMovers.rows),
      directionAvailable: dsMovers.baselineAvailable && booneMovers.baselineAvailable,
      baselineDs: ds.baselineTimes,
      baselineBoone: boone.baselineTimes,
      freshest: ds.current.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
    }
  }, [dsRows, booneRows, scoring, timeframe])

  const matchesPos = (p: string) => pos === 'ALL' || p === pos
  const currentRows = useMemo(() => data.currentRows.filter(r => matchesPos(r.position)).slice(0, LIST_SIZE), [data, pos])
  const directionRows = useMemo(() => data.directionRows.filter(r => matchesPos(r.position)).slice(0, LIST_SIZE), [data, pos])

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-1">
            <button className={`btn ${view === 'current' ? 'btn-primary' : ''}`} onClick={() => setView('current')}>Current value</button>
            <button className={`btn ${view === 'direction' ? 'btn-primary' : ''}`} onClick={() => setView('direction')}>Direction of movement</button>
          </div>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {data.freshest && <span className="subtle ml-auto">Data as of {new Date(data.freshest).toLocaleString()}</span>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {view === 'direction' && (
            <div className="flex gap-1">
              {TIMEFRAMES.map(t => (
                <button key={t.id} className={`btn ${timeframe === t.id ? 'btn-primary' : ''}`} onClick={() => setTimeframe(t.id)}>{t.label}</button>
              ))}
            </div>
          )}
          <div className="flex gap-1">
            {POSITIONS.map(p => (
              <button key={p} className={`btn ${pos === p ? 'btn-primary' : ''}`} onClick={() => setPos(p)}>{p}</button>
            ))}
          </div>
        </div>
        <div className="subtle">
          Boone and Draft Sharks use different value scales, so gaps compare Boone mapped onto the Draft Sharks scale.
          {view === 'current' && ' Players ranked outside the top 150 in both sources are hidden.'}
          {view === 'direction' && ` A source counts as flat under 1.5 points of movement. ${describeBaseline('Draft Sharks', data.baselineDs)} · ${describeBaseline('Boone', data.baselineBoone)}.`}
        </div>
        {loading && <div className="subtle">Loading…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
      </div>

      {!loading && !error && view === 'current' && (
        <div className="card p-4">
          <table className="table">
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th className="text-right">DS rank</th>
                <th className="text-right">Boone rank</th>
                <th className="text-right">DS value</th>
                <th className="text-right">Boone (DS scale)</th>
                <th className="text-right">Boone raw</th>
                <th className="text-right">Gap</th>
              </tr>
            </thead>
            <tbody>
              {currentRows.map(r => (
                <tr key={`${r.canonicalName}::${r.position}`}>
                  <td>{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
                  <td>{r.position}</td>
                  <td className="text-right">{r.dsRank}</td>
                  <td className="text-right">{r.booneRank}</td>
                  <td className="text-right">{r1(r.dsValue)}</td>
                  <td className="text-right">{r1(r.booneScaled)}</td>
                  <td className="text-right subtle">{r.booneValue}</td>
                  <td className="text-right">
                    <span className={signClass(r.valueGap)}>{signed(r.valueGap)}</span>
                    <span className="subtle"> {r.valueGap > 0 ? 'Boone higher' : 'DS higher'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {currentRows.length === 0 && <div className="subtle">No players match.</div>}
        </div>
      )}

      {!loading && !error && view === 'direction' && !data.directionAvailable && (
        <div className="card p-4 subtle">
          Not enough history for this timeframe yet — both sources need a snapshot old enough to compare against.
        </div>
      )}

      {!loading && !error && view === 'direction' && data.directionAvailable && (
        <div className="card p-4">
          <table className="table">
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th className="text-right">Boone change</th>
                <th className="text-right">DS change</th>
                <th className="text-right">Difference</th>
              </tr>
            </thead>
            <tbody>
              {directionRows.map(r => (
                <tr key={`${r.canonicalName}::${r.position}`}>
                  <td>{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
                  <td>{r.position}</td>
                  <td className={`text-right ${signClass(r.booneChange)}`}>{signed(r.booneChange)}</td>
                  <td className={`text-right ${signClass(r.dsChange)}`}>{signed(r.dsChange)}</td>
                  <td className="text-right font-semibold">{r1(r.size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {directionRows.length === 0 && <div className="subtle">No direction disagreements.</div>}
        </div>
      )}
    </div>
  )
}
