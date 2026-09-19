import { useEffect, useMemo, useState } from 'react'
import { supabase, fetchAllRows, type RosRankingRow, type TradeValueLatestRow } from '../lib/supabase'
import { pivotTradeValues, sourcesWithData, type Scoring, type TradeValueSourceRow } from '../lib/tradeValues'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const FANTASY_POSITIONS = new Set(POSITIONS.filter(p => p !== 'ALL'))
const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }

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

// Display-only niceties for sources discovered from the data -- never a
// gate on which sources appear, just how their column header reads.
const SOURCE_LABELS: Record<string, string> = {
  boone: 'Boone', draftsharks: 'DS 3D', cbs: 'CBS', fantasypros: 'FantasyPros', rsj: 'RSJ', usatoday: 'USA Today',
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

const nonNull = <T,>(x: T | null): x is T => x != null

// Draft Sharks has no trade-value chart of its own -- its "3D value" in the
// ROS rankings (ds_value) is the equivalent, so it joins the pivot as one more
// source. ROS rows are per scoring format, so only the active scoring's rows
// are used (labelled to match valueForScoring's PPR/HALF detection). Skips
// anything outside the four skill positions (no K/DST/IDP on this page).
function dsRosToSourceRow(r: RosRankingRow, scoring: Scoring): TradeValueSourceRow | null {
  if (r.scoring !== scoring || r.ds_value == null || !FANTASY_POSITIONS.has(r.position)) return null
  return {
    source: 'draftsharks',
    playerName: r.player_name,
    canonicalName: r.canonical_name,
    team: r.team,
    position: r.position,
    valueCol1Label: scoring === 'ppr' ? 'PPR' : 'HALF',
    valueCol1: r.ds_value,
    valueCol2Label: 'N/A',
    valueCol2: null,
  }
}

export default function TradeValues() {
  const [rows, setRows] = useState<TradeValueLatestRow[]>([])
  const [rosRows, setRosRows] = useState<RosRankingRow[]>([])
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
    // Paginated: all sources together exceed PostgREST's 1000-row cap, and a
    // plain .limit() just truncates (that's how USA Today went missing).
    Promise.all([
      fetchAllRows<TradeValueLatestRow>((from, to) =>
        supabase.from('in_season_trade_values_latest').select('*').order('id').range(from, to),
      ),
      fetchAllRows<RosRankingRow>((from, to) =>
        supabase.from('in_season_ros_rankings_latest').select('*').order('id').range(from, to),
      ),
    ]).then(([tvRes, rosRes]) => {
      if (cancelled) return
      const err = tvRes.error ?? rosRes.error
      if (err) setError(err.message)
      else {
        setRows(tvRes.data)
        setRosRows(rosRes.data)
      }
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [])

  const pivoted = useMemo(
    () => pivotTradeValues([...rows.map(toSourceRow), ...rosRows.map(r => dsRosToSourceRow(r, scoring)).filter(nonNull)], scoring),
    [rows, rosRows, scoring],
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
        <ScoringToggle value={scoring} onChange={setScoring} />
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
              <th className="num">Score</th>
              {visibleSources.map(s => <th key={s} className="num">{sourceLabel(s)}</th>)}
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
