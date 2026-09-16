import React, { useEffect, useMemo, useState } from 'react'
import { supabase, type RankingLatestRow } from '../lib/supabase'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SOURCES = ['ALL', 'draftsharks', 'boone', 'smythe']
const SCORINGS = ['ppr', 'half-ppr']

export default function Rankings() {
  const [rows, setRows] = useState<RankingLatestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pos, setPos] = useState('ALL')
  const [source, setSource] = useState('ALL')
  const [scoring, setScoring] = useState<'ppr' | 'half-ppr'>('ppr')
  const [query, setQuery] = useState('')
  const [week, setWeek] = useState<number | null>(null)
  const [weeks, setWeeks] = useState<number[]>([])

  // Boone/Smythe only ever publish the current (and sometimes next) week,
  // while Draft Sharks publishes rankings for every remaining week at once.
  // So "latest" isn't one row per player -- default the week picker to
  // whatever Boone/Smythe consider current, and let the user browse others.
  useEffect(() => {
    let cancelled = false
    supabase
      .from('in_season_rankings_latest')
      .select('week')
      .in('source', ['boone', 'smythe'])
      .order('week', { ascending: false })
      .limit(1)
      .then(({ data }) => {
        if (cancelled) return
        const current = data?.[0]?.week ?? null
        setWeek(current)
      })
    // Draft Sharks publishes every remaining week (1-18) in one pull, so
    // that's the full range of weeks that can ever show up here.
    setWeeks(Array.from({ length: 18 }, (_, i) => i + 1))
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (week == null) return
    let cancelled = false
    setLoading(true)
    setError(null)

    let q = supabase
      .from('in_season_rankings_latest')
      .select('*')
      .eq('scoring', scoring)
      .eq('week', week)
      .order('rank', { ascending: true, nullsFirst: false })
      .limit(1000)

    if (pos !== 'ALL') q = q.eq('position', pos)
    if (source !== 'ALL') q = q.eq('source', source)

    q.then(({ data, error }) => {
      if (cancelled) return
      if (error) setError(error.message)
      else setRows((data ?? []) as RankingLatestRow[])
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [pos, source, scoring, week])

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
        <select className="input" value={scoring} onChange={e => setScoring(e.target.value as any)}>
          {SCORINGS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input" value={week ?? ''} onChange={e => setWeek(Number(e.target.value))}>
          {weeks.map(w => <option key={w} value={w}>Week {w}</option>)}
        </select>
        {freshest && <span className="subtle ml-auto">Data as of {new Date(freshest).toLocaleString()}</span>}
      </div>

      {loading && <div className="subtle">Loading rankings…</div>}
      {error && <div className="text-red-400">Failed to load: {error}</div>}

      {!loading && !error && (
        <table className="table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Player</th>
              <th>Team</th>
              <th>Pos</th>
              <th>Source</th>
              <th>Proj</th>
              <th>Floor</th>
              <th>Ceiling</th>
              <th>Opp</th>
              <th>Week</th>
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
                <td className="text-right">{r.projection ?? ''}</td>
                <td className="text-right">{r.floor_proj ?? ''}</td>
                <td className="text-right">{r.ceiling_proj ?? ''}</td>
                <td>{r.opponent ?? ''}</td>
                <td>{r.week}</td>
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
