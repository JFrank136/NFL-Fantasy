import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useComparisonPool } from '../lib/useComparisonPool'
import { useWeeklyRows } from '../lib/useWeeklyRows'
import type { Scoring } from '../lib/useBlendedRos'
import { buildWeeklyPool } from '../lib/weeklyPool'
import { formatCell, round1, type ComparisonPlayer } from '../lib/playerComparison'
import { addDropRows, analyzeAddDrop } from '../lib/addDrop'

const MAX_PER_LIST = 5

export default function AddDrop() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [addKeys, setAddKeys] = useState<string[]>([])
  const [dropKeys, setDropKeys] = useState<string[]>([])
  const { pool, freshest, loading, error } = useComparisonPool(scoring)
  // This week's outlook is secondary context, so it never blocks or fails the page.
  const weekly = useWeeklyRows(scoring)

  const byKey = useMemo(() => new Map(pool.map(p => [p.key, p])), [pool])
  const weeklyByKey = useMemo(() => new Map(buildWeeklyPool(weekly.rows).map(p => [p.key, p])), [weekly.rows])

  const resolve = (keys: string[]) => keys.map(k => byKey.get(k)).filter((p): p is ComparisonPlayer => !!p)
  const adds = useMemo(() => resolve(addKeys), [addKeys, byKey])
  const drops = useMemo(() => resolve(dropKeys), [dropKeys, byKey])
  const all = useMemo(() => [...adds, ...drops], [adds, drops])

  const candidates = useMemo(
    () => pool.filter(p => !addKeys.includes(p.key) && !dropKeys.includes(p.key)),
    [pool, addKeys, dropKeys],
  )

  const rows = useMemo(() => addDropRows(all, weeklyByKey), [all, weeklyByKey])
  const analysis = useMemo(() => analyzeAddDrop(adds, drops), [adds, drops])

  const remove = (key: string) => {
    setAddKeys(prev => prev.filter(k => k !== key))
    setDropKeys(prev => prev.filter(k => k !== key))
  }

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Add/Drop -- is anyone worth adding, and who should go?</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {all.length > 0 && <button className="btn ml-auto" onClick={() => { setAddKeys([]); setDropKeys([]) }}>Clear</button>}
          {freshest && <span className="subtle">Data as of {new Date(freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading player values…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}

        {!loading && !error && (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <span className="label">Add candidates (waiver wire)</span>
              <PlayerPicker
                candidates={candidates}
                disabled={adds.length >= MAX_PER_LIST}
                placeholder={adds.length >= MAX_PER_LIST ? `Max ${MAX_PER_LIST} adds` : 'Add a waiver player…'}
                onAdd={p => setAddKeys(prev => (prev.length >= MAX_PER_LIST ? prev : [...prev, p.key]))}
              />
            </div>
            <div className="space-y-1">
              <span className="label">Drop candidates (my bench)</span>
              <PlayerPicker
                candidates={candidates}
                disabled={drops.length >= MAX_PER_LIST}
                placeholder={drops.length >= MAX_PER_LIST ? `Max ${MAX_PER_LIST} drops` : 'Add a bench player…'}
                onAdd={p => setDropKeys(prev => (prev.length >= MAX_PER_LIST ? prev : [...prev, p.key]))}
              />
            </div>
          </div>
        )}
      </div>

      {!loading && !error && all.length > 0 && (
        <div className="card p-4 space-y-3">
          <ComparisonTable
            columns={all.map(p => ({
              key: p.key,
              header: (
                <span>
                  {p.playerName}{' '}
                  <button
                    className="subtle"
                    style={{ cursor: 'pointer' }}
                    onClick={() => remove(p.key)}
                    aria-label={`Remove ${p.playerName}`}
                  >
                    ✕
                  </button>
                </span>
              ),
              subheader: `${addKeys.includes(p.key) ? 'ADD' : 'DROP'} · ${p.position}${p.team ? ` · ${p.team}` : ''}`,
            }))}
            rows={rows.map(r => ({
              id: r.id,
              label: r.label,
              cells: r.values.map((v, i) => ({ text: formatCell(v, r.format), highlight: r.highlights[i] })),
            }))}
          />
          <div className="subtle">
            ROS value answers "who is better right now"; ceiling answers "who has the better best case". They are shown separately on purpose.
            This week's rows and strength of schedule are context only. Weekly position rank is highlighted only when everyone shares a position.
          </div>
        </div>
      )}

      {!loading && !error && analysis.status === 'ok' && analysis.bestAdd && analysis.dropTarget && (
        <div className="card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="label">1. Worth adding?</span>
              <span className="btn" style={{ cursor: 'default' }}>{analysis.verdict}</span>
            </div>
            <div>
              {analysis.bestAdd.playerName} ({round1(analysis.bestAdd.blended as number)}) vs {analysis.dropTarget.playerName} ({round1(analysis.dropTarget.blended as number)}):{' '}
              {(analysis.gap as number) > 0 ? '+' : ''}{round1(analysis.gap as number)} ROS value.
            </div>
            {analysis.upsideNote && <div className="subtle">{analysis.upsideNote}</div>}
          </div>
          <div className="space-y-1">
            <span className="label">2. If you add, drop</span>
            <div>{analysis.dropTarget.playerName} <span className="subtle">{analysis.dropTarget.position}{analysis.dropTarget.team ? ` · ${analysis.dropTarget.team}` : ''}</span></div>
            {analysis.dropCaveat && <div className="subtle">{analysis.dropCaveat}</div>}
          </div>
        </div>
      )}

      {!loading && !error && all.length > 0 && analysis.status === 'insufficient' && (
        <div className="card p-4 subtle">Pick at least one add candidate and one drop candidate to see a verdict.</div>
      )}

      {!loading && !error && all.length === 0 && (
        <div className="card p-4 subtle">Search for players above: waiver targets on the left, your bench on the right.</div>
      )}
    </div>
  )
}
