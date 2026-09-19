import { useMemo, useState } from 'react'
import { useBlendedRos, type Scoring } from '../lib/useBlendedRos'
import { identityKey, type BlendedRosRow } from '../lib/blend'
import { evaluateTrade, buildExtraSourceValues, tradeSourceLabel, type TradeComparison } from '../lib/tradeAnalyzer'
import { useTradeValueRows } from '../lib/useTradeValueRows'

const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }
const MAX_PLAYERS_PER_SIDE = 4

type SideKey = 'A' | 'B'
const sideName = (side: SideKey) => `Side ${side}`
const sideColor = (side: SideKey) => (side === 'A' ? 'var(--side-a)' : 'var(--side-b)')

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
  const [focused, setFocused] = useState(false)

  const searching = query.trim().length >= 2
  const matches = useMemo(() => {
    if (!searching) return []
    const q = query.trim().toLowerCase()
    return candidates.filter(r => r.playerName.toLowerCase().includes(q)).slice(0, 8)
  }, [candidates, query, searching])

  return (
    <div className="relative">
      <input
        className="input w-full"
        placeholder={disabled ? `Max ${MAX_PLAYERS_PER_SIDE} players` : 'Search a player to add…'}
        value={query}
        disabled={disabled}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {!disabled && focused && searching && (
        <div className="search-results">
          {matches.length === 0 && <div className="px-3 py-2 text-sm">No matching players.</div>}
          {matches.map(r => (
            <div
              key={identityKey(r.canonicalName, r.position)}
              className="search-result"
              onMouseDown={() => { onAdd(r); setQuery('') }}
            >
              <span>{r.playerName}</span>
              <span className="search-result-meta">{r.team ?? 'FA'} · {r.position}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TradeSide({
  side,
  players,
  totalValue,
  bestPlayerKey,
  status,
  candidates,
  onAdd,
  onRemove,
}: {
  side: SideKey
  players: BlendedRosRow[]
  totalValue: number | null
  bestPlayerKey: string | null
  status: 'winner' | 'loser' | 'neutral'
  candidates: BlendedRosRow[]
  onAdd: (row: BlendedRosRow) => void
  onRemove: (key: string) => void
}) {
  const cls = ['trade-side', side === 'A' ? 'trade-side-a' : 'trade-side-b']
  if (status === 'winner') cls.push('trade-side-winner')
  if (status === 'loser') cls.push('trade-side-loser')

  return (
    <div className={cls.join(' ')}>
      <div className="trade-side-header">
        <span className="trade-side-title">{sideName(side)}</span>
        {status === 'winner' && <span className="winner-badge">★ Winner</span>}
      </div>

      <div className="p-4 space-y-3">
        <PlayerPicker candidates={candidates} disabled={players.length >= MAX_PLAYERS_PER_SIDE} onAdd={onAdd} />

        <div className="space-y-2">
          {players.length === 0 && <div className="subtle py-2">No players added yet.</div>}
          {players.map(p => {
            const key = identityKey(p.canonicalName, p.position)
            return (
              <div key={key} className="player-chip">
                <div>
                  <div className={key === bestPlayerKey ? 'font-bold' : 'font-semibold'}>{p.playerName}</div>
                  <div className="subtle">{p.position}{p.team ? ` · ${p.team}` : ''}</div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="font-bold">{p.blendedValue != null ? Math.round(p.blendedValue) : '—'}</div>
                    <div className="subtle">DS {p.dsValue ?? '—'} · Boone {p.booneValue ?? '—'}</div>
                  </div>
                  <button className="btn" onClick={() => onRemove(key)} aria-label={`Remove ${p.playerName}`}>✕</button>
                </div>
              </div>
            )
          })}
        </div>

        <div className="flex items-end justify-between pt-3" style={{ borderTop: '1px solid var(--bg-card-border)' }}>
          <span className="subtle">Total blended value</span>
          <span className="side-total">{totalValue != null ? Math.round(totalValue) : '—'}</span>
        </div>
      </div>
    </div>
  )
}

const fmt = (n: number | null) => (n != null ? Math.round(n).toLocaleString() : '—')

/** One side's cell in the comparison table. The winning cell gets a colored
 * fill; a "2/3" note flags a side missing this source's value for some player
 * (its total is understated). */
function ValueCell({ total, valued, size, wins, side }: { total: number | null; valued: number; size: number; wins: boolean; side: SideKey }) {
  return (
    <td className={wins ? (side === 'A' ? 'win-a' : 'win-b') : undefined}>
      {fmt(total)}
      {total != null && valued < size && (
        <span className="subtle ml-1" title="Some players have no value from this source">({valued}/{size})</span>
      )}
    </td>
  )
}

function EdgeCell({ winner, pctDiff }: { winner: SideKey | null; pctDiff: number | null }) {
  if (!winner || pctDiff == null) return <td className="subtle">—</td>
  return (
    <td className={`font-bold ${winner === 'A' ? 'edge-a' : 'edge-b'}`}>
      {sideName(winner)} +{Math.round(pctDiff * 100)}%
    </td>
  )
}

function Verdict({ comparison }: { comparison: TradeComparison }) {
  const { preferredSide, confidence, pctDiff, sources } = comparison
  const ready = comparison.diff != null

  const decided = sources.filter(s => s.winner != null)
  const winsA = decided.filter(s => s.winner === 'A').length
  const winsB = decided.filter(s => s.winner === 'B').length

  return (
    <div className="verdict-panel">
      <div className="verdict-header">
        <span className="label" style={{ color: 'var(--accent-gold)' }}>Verdict</span>
        {!ready && <span className="subtle">{comparison.summary}</span>}
        {ready && preferredSide && (
          <span className="verdict-headline" style={{ color: sideColor(preferredSide) }}>
            {sideName(preferredSide)} wins
          </span>
        )}
        {ready && !preferredSide && <span className="verdict-headline">Even trade</span>}
        {ready && confidence && (
          <span className="badge" style={{ borderColor: 'var(--accent-gold)', color: 'var(--accent-gold)' }}>{confidence} confidence</span>
        )}
        {ready && pctDiff != null && <span className="subtle">{Math.round(pctDiff * 100)}% blended difference</span>}
      </div>

      {ready && (
        <div className="p-4 space-y-3">
          <div>{comparison.summary}</div>

          <div className="overflow-x-auto">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th style={{ color: sideColor('A') }}>{sideName('A')}</th>
                  <th style={{ color: sideColor('B') }}>{sideName('B')}</th>
                  <th>Edge</th>
                </tr>
              </thead>
              <tbody>
                <tr className="blended-row">
                  <td>Blended <span className="subtle">(overall)</span></td>
                  <ValueCell total={comparison.sideA.totalValue} valued={comparison.sideA.players.length} size={comparison.sideA.players.length} wins={preferredSide === 'A'} side="A" />
                  <ValueCell total={comparison.sideB.totalValue} valued={comparison.sideB.players.length} size={comparison.sideB.players.length} wins={preferredSide === 'B'} side="B" />
                  <EdgeCell winner={preferredSide} pctDiff={pctDiff} />
                </tr>
                {sources.map(src => (
                  <tr key={src.source}>
                    <td>{tradeSourceLabel(src.source)}</td>
                    <ValueCell total={src.totalA} valued={src.valuedA} size={src.sizeA} wins={src.winner === 'A'} side="A" />
                    <ValueCell total={src.totalB} valued={src.valuedB} size={src.sizeB} wins={src.winner === 'B'} side="B" />
                    <EdgeCell winner={src.winner} pctDiff={src.pctDiff} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {decided.length > 0 && (
            <div className="subtle">
              Individual sources: <span className="edge-a font-bold">{sideName('A')} leads {winsA}</span> · <span className="edge-b font-bold">{sideName('B')} leads {winsB}</span> of {decided.length}.
              Each source uses its own scale, so compare {sideName('A')} against {sideName('B')} within a row, not across rows.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TradeAnalyzer() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const { rows, loading, error, freshest } = useBlendedRos(scoring)
  const { rows: tradeValueRows } = useTradeValueRows()
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

  const extraSourceValues = useMemo(() => buildExtraSourceValues(tradeValueRows, scoring), [tradeValueRows, scoring])
  const comparison = useMemo(
    () => evaluateTrade(sideAPlayers, sideBPlayers, extraSourceValues),
    [sideAPlayers, sideBPlayers, extraSourceValues],
  )

  const statusFor = (side: SideKey) =>
    comparison.preferredSide == null ? 'neutral' : comparison.preferredSide === side ? 'winner' : 'loser'

  const addTo = (side: SideKey) => (row: BlendedRosRow) => {
    const key = identityKey(row.canonicalName, row.position)
    const setKeys = side === 'A' ? setSideAKeys : setSideBKeys
    setKeys(prev => (prev.length >= MAX_PLAYERS_PER_SIDE ? prev : [...prev, key]))
  }
  const removeFrom = (side: SideKey) => (key: string) => {
    const setKeys = side === 'A' ? setSideAKeys : setSideBKeys
    setKeys(prev => prev.filter(k => k !== key))
  }

  const reset = () => { setSideAKeys([]); setSideBKeys([]) }

  const bestAKey = comparison.sideA.bestPlayer ? identityKey(comparison.sideA.bestPlayer.canonicalName, comparison.sideA.bestPlayer.position) : null
  const bestBKey = comparison.sideB.bestPlayer ? identityKey(comparison.sideB.bestPlayer.canonicalName, comparison.sideB.bestPlayer.position) : null

  return (
    <div className="space-y-5">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Trade Analyzer -- compares total blended ROS value (50% Draft Sharks / 50% Boone), with each source's own totals below.</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          <button className="btn ml-auto" onClick={reset}>Reset</button>
          {freshest && <span className="subtle">Data as of {new Date(freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading player values…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
      </div>

      {!loading && !error && (
        <>
          <div className="grid md:grid-cols-2 gap-5">
            <TradeSide
              side="A"
              players={sideAPlayers}
              totalValue={comparison.sideA.totalValue}
              bestPlayerKey={bestAKey}
              status={statusFor('A')}
              candidates={candidates}
              onAdd={addTo('A')}
              onRemove={removeFrom('A')}
            />
            <TradeSide
              side="B"
              players={sideBPlayers}
              totalValue={comparison.sideB.totalValue}
              bestPlayerKey={bestBKey}
              status={statusFor('B')}
              candidates={candidates}
              onAdd={addTo('B')}
              onRemove={removeFrom('B')}
            />
          </div>

          <Verdict comparison={comparison} />
        </>
      )}
    </div>
  )
}
