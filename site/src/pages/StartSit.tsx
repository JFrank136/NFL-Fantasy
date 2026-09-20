import { useEffect, useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useWeeklyRows } from '../lib/useWeeklyRows'
import { useComparisonPool } from '../lib/useComparisonPool'
import type { Scoring } from '../lib/useBlendedRos'
import { buildWeeklyPool, type WeeklyPlayer } from '../lib/weeklyPool'
import { formatCell } from '../lib/playerComparison'
import { recommendStartSit, startSitRows } from '../lib/startSit'

const MIN_PLAYERS = 2
const MAX_PLAYERS = 5

export default function StartSit() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const weekly = useWeeklyRows(scoring)
  // ROS value is context only, so it never blocks or fails the page.
  const ros = useComparisonPool(scoring)

  const pool = useMemo(() => buildWeeklyPool(weekly.rows, weekly.week), [weekly.rows, weekly.week])
  const rosByKey = useMemo(() => new Map(ros.pool.map(p => [p.key, p.blended])), [ros.pool])
  const byKey = useMemo(() => new Map(pool.map(p => [p.key, p])), [pool])

  // Drop selections the reloaded pool no longer contains: a ghost key keeps
  // filtering the picker and keeps "Clear" hidden with nothing on screen.
  // Only while the pool is populated -- an empty pool means "still loading".
  useEffect(() => {
    if (byKey.size === 0) return
    setSelectedKeys(prev => {
      const next = prev.filter(k => byKey.has(k))
      return next.length === prev.length ? prev : next
    })
  }, [byKey])

  const selected = useMemo(
    () => selectedKeys.map(k => byKey.get(k)).filter((p): p is WeeklyPlayer => !!p),
    [selectedKeys, byKey],
  )
  const candidates = useMemo(
    () => pool
      .filter(p => !selectedKeys.includes(p.key))
      .map(p => ({ key: p.key, playerName: p.playerName, position: p.position, team: p.team, blended: null,
        detail: p.isBye ? 'BYE'
          : p.flexRank != null ? `FLEX #${p.flexRank}`
          : p.positionRank != null ? `${p.position} #${p.positionRank}`
          : null,
      })),
    [pool, selectedKeys],
  )

  const rows = useMemo(() => startSitRows(selected, rosByKey), [selected, rosByKey])
  const rec = useMemo(() => recommendStartSit(selected), [selected])
  const starter = rec.starterKey ? byKey.get(rec.starterKey) : undefined

  const { loading, error } = weekly

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Start/Sit -- compare {MIN_PLAYERS}–{MAX_PLAYERS} players for this week's lineup.</span>
          <span className="btn btn-primary" style={{ cursor: 'default' }}>Week {weekly.week ?? '…'}</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {selected.length > 0 && <button className="btn ml-auto" onClick={() => setSelectedKeys([])}>Clear</button>}
          {weekly.freshest && <span className="subtle">Data as of {new Date(weekly.freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading weekly rankings…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}

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
                  {p.playerName}
                  {p.key === rec.starterKey && <span style={{ color: 'var(--signal-up)' }}> ✓ Start</span>}{' '}
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
              subheader: `${p.position}${p.team ? ` · ${p.team}` : ''}${p.isBye ? ' · BYE' : ''}`,
            }))}
            rows={rows.map(r => ({
              id: r.id,
              label: r.label,
              cells: r.values.map((v, i) => ({ text: formatCell(v, r.format), highlight: r.highlights[i] })),
            }))}
          />
          <div className="subtle">
            The rank score is a weighted average of Draft Sharks, Boone and Smyth ranks. Draft Sharks publishes one overall weekly rank (kickers,
            defenses and IDP included), so it is re-ranked within RB/WR/TE and within QB first, putting all three sources on the same scale. The score
            is therefore comparable across RB/WR/TE — which is what FLEX rank uses — but a QB score is never comparable with an RB/WR/TE one, so nothing
            scale-dependent is highlighted in a mixed comparison. Position rank is only highlighted when everyone shares a position. Opponent and ROS
            value are context and don't affect the pick.
          </div>
        </div>
      )}

      {!loading && !error && rec.status === 'ok' && starter && (
        <div className="card p-4 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="label">Start</span>
            <span className="font-semibold">{starter.playerName}</span>
            <span className="subtle">{starter.position}{starter.team ? ` · ${starter.team}` : ''}</span>
            <span className="btn" style={{ cursor: 'default' }}>{rec.confidence}</span>
          </div>
          <ul className="list-disc pl-5 text-sm space-y-0.5">
            {rec.reasons.map(reason => <li key={reason}>{reason}</li>)}
          </ul>
          {rec.note && <div className="subtle">{rec.note}</div>}
        </div>
      )}

      {!loading && !error && selected.length > 0 && rec.status !== 'ok' && rec.note && (
        <div className="card p-4 subtle">{rec.note}</div>
      )}

      {!loading && !error && selected.length === 0 && (
        <div className="card p-4 subtle">Search for a player above to start comparing.</div>
      )}
    </div>
  )
}
