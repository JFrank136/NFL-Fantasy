import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useRosHistory } from '../lib/useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from '../lib/useBlendedRos'
import { blendRosValues, identityKey } from '../lib/blend'
import { buildMovers, splitSnapshots, TIMEFRAME_MIN_GAP_MS } from '../lib/movers'
import {
  buildComparisonPool, comparisonRows, summarizeComparison,
  type CellFormat, type ComparisonPlayer,
} from '../lib/playerComparison'

const MIN_PLAYERS = 2
const MAX_PLAYERS = 5

const r1 = (n: number) => Math.round(n * 10) / 10

function formatCell(value: number | string | null, format: CellFormat): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  switch (format) {
    case 'rank': return `#${value}`
    case 'signed': return `${value > 0 ? '+' : ''}${r1(value)}`
    default: return String(r1(value))
  }
}

export default function PlayerComparison() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)

  const { pool, freshest } = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS.latest
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    const current = { ds: ds.current.map(toDsRosInput), boone: boone.current.map(r => toBooneRosInput(r, scoring)) }

    const { rows: movers } = buildMovers('blended', current, {
      ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
      boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
    })
    const trendByKey = new Map(movers.map(m => [identityKey(m.canonicalName, m.position), m.change]))
    const sosByKey = new Map(ds.current.map(r => [identityKey(r.canonical_name, r.position), r.strength_of_schedule]))

    return {
      pool: buildComparisonPool(blendRosValues(current.ds, current.boone), trendByKey, sosByKey),
      freshest: ds.current.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
    }
  }, [dsRows, booneRows, scoring])

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
