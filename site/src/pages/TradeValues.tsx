import { useEffect, useMemo, useState } from 'react'
import { supabase, type TradeValueLatestRow } from '../lib/supabase'
import { pivotTradeValues, sourcesWithData, type Scoring, type TradeValueSourceRow } from '../lib/tradeValues'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }

// Display-only niceties for sources discovered from the data -- never a
// gate on which sources appear, just how their column header reads.
const SOURCE_LABELS: Record<string, string> = {
  boone: 'Boone', cbs: 'CBS', fantasypros: 'FantasyPros', rsj: 'RSJ', usatoday: 'USA Today',
}
const sourceLabel = (s: string) => SOURCE_LABELS[s] ?? s

function toSourceRow(r: TradeValueLatestRow): TradeValueSourceRow {
  return {
    source: r.source,
    playerName: r.player_name,
    canonicalName: r.canonical_name,
    team: r.team,
    position: r.position,
    valueCol1Label: r.value_col1_label,
    valueCol1: r.value_col1,
    valueCol2Label: r.value_col2_label,
    valueCol2: r.value_col2,
  }
}

export default function TradeValues() {
  const [rows, setRows] = useState<TradeValueLatestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pos, setPos] = useState('ALL')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [query, setQuery] = useState('')
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    // Fetch every source/position -- the pivot needs all of them at once to
    // build one row per player and to compute each source's percentile
    // distribution, so position/source filtering happens client-side below.
    supabase
      .from('in_season_trade_values_latest')
      .select('*')
      .limit(5000)
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) setError(error.message)
        else setRows((data ?? []) as TradeValueLatestRow[])
        setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  const pivoted = useMemo(
    () => pivotTradeValues(rows.map(toSourceRow), scoring),
    [rows, scoring],
  )

  const availableSources = useMemo(() => sourcesWithData(pivoted), [pivoted])
  const visibleSources = useMemo(
    () => availableSources.filter(s => !hiddenSources.has(s)),
    [availableSources, hiddenSources],
  )

  const display = useMemo(() => {
    let list = pivoted
    if (pos !== 'ALL') list = list.filter(r => r.position === pos)
    if (query) {
      const q = query.toLowerCase()
      list = list.filter(r => r.playerName.toLowerCase().includes(q))
    }
    return list
  }, [pivoted, pos, query])

  const freshest = useMemo(() => {
    if (!rows.length) return null
    return rows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), rows[0].pulled_at)
  }, [rows])

  const toggleSource = (source: string) => {
    setHiddenSources(prev => {
      const next = new Set(prev)
      if (next.has(source)) next.delete(source)
      else next.add(source)
      return next
    })
  }

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input className="input" placeholder="Search players..." value={query} onChange={e => setQuery(e.target.value)} />
        <div className="flex gap-1">
          {POSITIONS.map(p => (
            <button key={p} className={`btn ${pos === p ? 'btn-primary' : ''}`} onClick={() => setPos(p)}>{p}</button>
          ))}
        </div>
        <select className="input" value={scoring} onChange={e => setScoring(e.target.value as Scoring)}>
          {SCORINGS.map(s => <option key={s} value={s}>{SCORING_LABELS[s]}</option>)}
        </select>
        {freshest && <span className="subtle ml-auto">Data as of {new Date(freshest).toLocaleString()}</span>}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span className="subtle">Sources:</span>
        {availableSources.map(s => (
          <button
            key={s}
            className={`btn ${!hiddenSources.has(s) ? 'btn-primary' : ''}`}
            onClick={() => toggleSource(s)}
            title={hiddenSources.has(s) ? 'Hidden -- click to show' : 'Shown -- click to hide'}
          >
            {sourceLabel(s)}
          </button>
        ))}
      </div>

      {loading && <div className="subtle">Loading trade values…</div>}
      {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}

      {!loading && !error && (
        <table className="table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Player</th>
              <th>Team</th>
              <th>Pos</th>
              <th>Score</th>
              {visibleSources.map(s => <th key={s}>{sourceLabel(s)}</th>)}
            </tr>
          </thead>
          <tbody>
            {display.map(r => (
              <tr key={`${r.canonicalName}__${r.position}`}>
                <td>{r.rank ?? ''}</td>
                <td>{r.playerName}</td>
                <td>{r.team ?? ''}</td>
                <td>{r.position}</td>
                <td className="text-right font-semibold">
                  {r.normalizedScore != null ? Math.round(r.normalizedScore) : ''}
                </td>
                {visibleSources.map(s => (
                  <td key={s} className="text-right">
                    {r.valuesBySource[s] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && !error && display.length === 0 && (
        <div className="subtle">No rows match these filters.</div>
      )}
    </div>
  )
}
