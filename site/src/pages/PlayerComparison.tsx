import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useComparisonPool } from '../lib/useComparisonPool'
import type { Scoring } from '../lib/useBlendedRos'
import {
  comparisonRows, formatCell, summarizeComparison,
  type ComparisonPlayer,
} from '../lib/playerComparison'

const MIN_PLAYERS = 2
const MAX_PLAYERS = 5

export default function PlayerComparison() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const { pool, freshest, loading, error, boonePending, currentWeek } = useComparisonPool(scoring)

  const byKey = useMemo(() => new Map(pool.map(p => [p.key, p])), [pool])
  const selected = useMemo(
    () => selectedKeys.map(k => byKey.get(k)).filter((p): p is ComparisonPlayer => !!p),
    [selectedKeys, byKey],
  )
  const candidates = useMemo(() => pool.filter(p => !selectedKeys.includes(p.key)), [pool, selectedKeys])

  const rows = useMemo(() => comparisonRows(selected), [selected])
  const summary = useMemo(() => summarizeComparison(selected), [selected])

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Player Comparison -- compare {MIN_PLAYERS}–{MAX_PLAYERS} players on rest-of-season value.</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {selected.length > 0 && <button className="btn ml-auto" onClick={() => setSelectedKeys([])}>Clear</button>}
          {freshest && <span className="subtle">Data as of {new Date(freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading player values…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
        {!loading && !error && boonePending && (
          <div className="subtle">Boone hasn't updated ROS values for Week {currentWeek} yet -- values below are Draft Sharks only until it does.</div>
        )}

        {!loading && !error && (
          <PlayerPicker
            candidates={candidates}
            disabled={selected.length >= MAX_PLAYERS}
            placeholder={selected.length >= MAX_PLAYERS ? `Max ${MAX_PLAYERS} players` : 'Add a player…'}
            onAdd={p => setSelectedKeys(prev => (prev.length >= MAX_PLAYERS ? prev : [...prev, p.key]))}
          />
        )}
      </div>

      {!loading && !error && selected.length > 0 && (
        <div className="card p-4 space-y-3">
          <ComparisonTable
            columns={selected.map(p => ({
              key: p.key,
              header: (
                <span>
                  {p.playerName}{' '}
                  <button
                    className="subtle"
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelectedKeys(prev => prev.filter(k => k !== p.key))}
                    aria-label={`Remove ${p.playerName}`}
                  >
                    ✕
                  </button>
                </span>
              ),
              subheader: `${p.position}${p.team ? ` · ${p.team}` : ''}`,
            }))}
            rows={rows.map(r => ({
              id: r.id,
              label: r.label,
              cells: r.values.map((v, i) => ({ text: formatCell(v, r.format), highlight: r.highlights[i] })),
            }))}
          />
          <div className="subtle">
            Strength of schedule is Draft Sharks' figure, shown as context only. Position rank is highlighted only when every player shares a position.
          </div>
        </div>
      )}

      {!loading && !error && selected.length >= MIN_PLAYERS && (
        <div className="card p-4 space-y-1">
          <span className="label">Summary</span>
          <div>{summary}</div>
        </div>
      )}

      {!loading && !error && selected.length === 0 && (
        <div className="card p-4 subtle">Search for a player above to start comparing.</div>
      )}
    </div>
  )
}
