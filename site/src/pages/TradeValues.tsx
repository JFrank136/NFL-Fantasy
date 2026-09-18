import { useEffect, useMemo, useState } from 'react'
import { supabase, type TradeValueLatestRow } from '../lib/supabase'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SOURCES = ['ALL', 'boone', 'cbs', 'fantasypros', 'rsj', 'usatoday']

export default function TradeValues() {
  const [rows, setRows] = useState<TradeValueLatestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pos, setPos] = useState('ALL')
  const [source, setSource] = useState('ALL')
  const [query, setQuery] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    let q = supabase
      .from('in_season_trade_values_latest')
      .select('*')
      .order('rank', { ascending: true, nullsFirst: false })
      .limit(1000)

    if (pos !== 'ALL') q = q.eq('position', pos)
    if (source !== 'ALL') q = q.eq('source', source)

    q.then(({ data, error }) => {
      if (cancelled) return
      if (error) setError(error.message)
      else setRows((data ?? []) as TradeValueLatestRow[])
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [pos, source])

  const display = useMemo(() => {
    if (!query) return rows
    const q = query.toLowerCase()
    return rows.filter(r => r.player_name.toLowerCase().includes(q))
  }, [rows, query])

  const freshest = useMemo(() => {
    if (!rows.length) return null
    return rows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), rows[0].pulled_at)
  }, [rows])

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input className="input" placeholder="Search players..." value={query} onChange={e => setQuery(e.target.value)} />
        <select className="input" value={pos} onChange={e => setPos(e.target.value)}>
          {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="input" value={source} onChange={e => setSource(e.target.value)}>
          {SOURCES.map(s => <option key={s} value={s}>{s === 'ALL' ? 'All sources' : s}</option>)}
        </select>
        {freshest && <span className="subtle ml-auto">Data as of {new Date(freshest).toLocaleString()}</span>}
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
              <th>Source</th>
              <th /* value_col1_label varies by position */>Value 1</th>
              <th>Value 2</th>
            </tr>
          </thead>
          <tbody>
            {display.map(r => (
              <tr key={r.id}>
                <td>{r.rank ?? ''}</td>
                <td>{r.player_name}</td>
                <td>{r.team ?? ''}</td>
                <td>{r.position}</td>
                <td>{r.source}</td>
                <td className="text-right">{r.value_col1_label}: {r.value_col1 ?? ''}</td>
                <td className="text-right">{r.value_col2_label}: {r.value_col2 ?? ''}</td>
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
