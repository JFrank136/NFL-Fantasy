import { useMemo, useState } from 'react'
import { useBlendedRos, type Scoring } from '../lib/useBlendedRos'
import { identityKey, type BlendedRosRow } from '../lib/blend'
import { evaluateTrade } from '../lib/tradeAnalyzer'

const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }
const MAX_PLAYERS_PER_SIDE = 4

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

function PlayerPicker({
  candidates,
  disabled,
  onAdd,
}: {
  candidates: BlendedRosRow[]
  disabled: boolean
  onAdd: (row: BlendedRosRow) => void
}) {
  const [query, setQuery] = useState('')

  const matches = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return candidates.filter(r => r.playerName.toLowerCase().includes(q)).slice(0, 8)
  }, [candidates, query])

  return (
    <div className="space-y-1">
      <input
        className="input w-full"
        placeholder={disabled ? `Max ${MAX_PLAYERS_PER_SIDE} players` : 'Add a player…'}
        value={query}
        disabled={disabled}
        onChange={e => setQuery(e.target.value)}
      />
      {!disabled && matches.length > 0 && (
        <div className="card p-1 space-y-0.5">
          {matches.map(r => (
            <div
              key={identityKey(r.canonicalName, r.position)}
              className="px-2 py-1.5 rounded-lg cursor-pointer flex items-center justify-between text-sm"
              style={{ background: 'transparent' }}
              onMouseDown={() => { onAdd(r); setQuery('') }}
            >
              <span>{r.playerName} <span className="subtle">{r.position}{r.team ? ` · ${r.team}` : ''}</span></span>
              <span className="subtle">{r.blendedValue != null ? Math.round(r.blendedValue) : '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TradeSide({
  label,
  players,
  totalValue,
  bestPlayerKey,
  highlight,
  candidates,
  onAdd,
  onRemove,
}: {
  label: string
  players: BlendedRosRow[]
  totalValue: number | null
  bestPlayerKey: string | null
  highlight: boolean
  candidates: BlendedRosRow[]
  onAdd: (row: BlendedRosRow) => void
  onRemove: (key: string) => void
}) {
  return (
    <div className="card p-4 space-y-3" style={highlight ? { borderColor: 'var(--accent-gold)' } : undefined}>
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        {highlight && <span className="badge" style={{ borderColor: 'var(--accent-gold)', color: 'var(--accent-gold)' }}>Favored</span>}
      </div>

      <PlayerPicker candidates={candidates} disabled={players.length >= MAX_PLAYERS_PER_SIDE} onAdd={onAdd} />

      <div className="space-y-1">
        {players.length === 0 && <div className="subtle">No players added yet.</div>}
        {players.map(p => {
          const key = identityKey(p.canonicalName, p.position)
          return (
            <div key={key} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg" style={{ background: 'var(--bg-page)' }}>
              <div>
                <div className={key === bestPlayerKey ? 'font-semibold' : ''}>{p.playerName}</div>
                <div className="subtle">{p.position}{p.team ? ` · ${p.team}` : ''}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="font-semibold">{p.blendedValue != null ? Math.round(p.blendedValue) : '—'}</div>
                  <div className="subtle">DS {p.dsValue ?? '—'} · Boone {p.booneValue ?? '—'}</div>
                </div>
                <button className="btn" onClick={() => onRemove(key)} aria-label={`Remove ${p.playerName}`}>✕</button>
              </div>
            </div>
          )
        })}
      </div>

      <div className="flex items-center justify-between pt-2" style={{ borderTop: '1px solid var(--bg-card-border)' }}>
        <span className="subtle">Total blended value</span>
        <span className="font-semibold text-lg">{totalValue != null ? Math.round(totalValue) : '—'}</span>
      </div>
    </div>
  )
}

export default function TradeAnalyzer() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const { rows, loading, error, freshest } = useBlendedRos(scoring)
  const [sideAKeys, setSideAKeys] = useState<string[]>([])
  const [sideBKeys, setSideBKeys] = useState<string[]>([])

  const byKey = useMemo(() => {
    const m = new Map<string, BlendedRosRow>()
    rows.forEach(r => m.set(identityKey(r.canonicalName, r.position), r))
    return m
  }, [rows])

  const sideAPlayers = useMemo(() => sideAKeys.map(k => byKey.get(k)).filter((r): r is BlendedRosRow => !!r), [sideAKeys, byKey])
  const sideBPlayers = useMemo(() => sideBKeys.map(k => byKey.get(k)).filter((r): r is BlendedRosRow => !!r), [sideBKeys, byKey])

  const usedKeys = useMemo(() => new Set([...sideAKeys, ...sideBKeys]), [sideAKeys, sideBKeys])
  const candidates = useMemo(() => rows.filter(r => !usedKeys.has(identityKey(r.canonicalName, r.position))), [rows, usedKeys])

  const comparison = useMemo(() => evaluateTrade(sideAPlayers, sideBPlayers), [sideAPlayers, sideBPlayers])

  const addTo = (side: 'A' | 'B') => (row: BlendedRosRow) => {
    const key = identityKey(row.canonicalName, row.position)
    if (side === 'A') setSideAKeys(prev => (prev.length >= MAX_PLAYERS_PER_SIDE ? prev : [...prev, key]))
    else setSideBKeys(prev => (prev.length >= MAX_PLAYERS_PER_SIDE ? prev : [...prev, key]))
  }
  const removeFrom = (side: 'A' | 'B') => (key: string) => {
    if (side === 'A') setSideAKeys(prev => prev.filter(k => k !== key))
    else setSideBKeys(prev => prev.filter(k => k !== key))
  }

  const reset = () => { setSideAKeys([]); setSideBKeys([]) }

  const bestAKey = comparison.sideA.bestPlayer ? identityKey(comparison.sideA.bestPlayer.canonicalName, comparison.sideA.bestPlayer.position) : null
  const bestBKey = comparison.sideB.bestPlayer ? identityKey(comparison.sideB.bestPlayer.canonicalName, comparison.sideB.bestPlayer.position) : null

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Trade Analyzer -- compares total blended ROS value (50% Draft Sharks / 50% Boone).</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          <button className="btn ml-auto" onClick={reset}>Reset</button>
          {freshest && <span className="subtle">Data as of {new Date(freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading player values…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
      </div>

      {!loading && !error && (
        <>
          <div className="grid md:grid-cols-2 gap-3">
            <TradeSide
              label="Side A"
              players={sideAPlayers}
              totalValue={comparison.sideA.totalValue}
              bestPlayerKey={bestAKey}
              highlight={comparison.preferredSide === 'A'}
              candidates={candidates}
              onAdd={addTo('A')}
              onRemove={removeFrom('A')}
            />
            <TradeSide
              label="Side B"
              players={sideBPlayers}
              totalValue={comparison.sideB.totalValue}
              bestPlayerKey={bestBKey}
              highlight={comparison.preferredSide === 'B'}
              candidates={candidates}
              onAdd={addTo('B')}
              onRemove={removeFrom('B')}
            />
          </div>

          <div className="card p-4 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="label">Verdict</span>
              {comparison.confidence && (
                <span className="badge">{comparison.confidence} confidence</span>
              )}
              {comparison.pctDiff != null && (
                <span className="subtle">{Math.round(comparison.pctDiff * 100)}% difference</span>
              )}
            </div>
            <div>{comparison.summary}</div>
          </div>
        </>
      )}
    </div>
  )
}
