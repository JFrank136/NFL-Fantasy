import { useEffect, useMemo, useState } from 'react'
import { supabase, type RankingLatestRow, type RosRankingRow, type TradeValueLatestRow } from '../lib/supabase'
import { blendRosValues, aggregateWeeklyRanks, type BlendedRosRow, type AggregatedWeeklyRow } from '../lib/blend'
import { fetchPreviousRosSnapshot } from '../lib/rosHistory'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
type Scoring = typeof SCORINGS[number]

type RosTabRow = BlendedRosRow & { rosChange: number | null }

function useCurrentWeek() {
  const [week, setWeek] = useState<number | null>(null)
  const [weeks] = useState<number[]>(Array.from({ length: 18 }, (_, i) => i + 1))

  useEffect(() => {
    let cancelled = false
    supabase
      .from('in_season_rankings_latest')
      .select('week')
      .in('source', ['boone', 'smythe'])
      .order('week', { ascending: false })
      .limit(1)
      .then(({ data }) => {
        if (!cancelled) setWeek(data?.[0]?.week ?? null)
      })
    return () => { cancelled = true }
  }, [])

  return { week, weeks }
}

function useRosTab(scoring: Scoring) {
  const [rows, setRows] = useState<RosTabRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      supabase.from('in_season_ros_rankings_latest').select('*').eq('scoring', scoring),
      supabase.from('in_season_trade_values_latest').select('*').eq('source', 'boone'),
    ]).then(async ([dsRes, booneRes]) => {
      if (cancelled) return
      if (dsRes.error) { setError(dsRes.error.message); setLoading(false); return }
      if (booneRes.error) { setError(booneRes.error.message); setLoading(false); return }

      const dsRows = (dsRes.data ?? []) as RosRankingRow[]
      const booneRows = (booneRes.data ?? []) as TradeValueLatestRow[]
      const currentPulledAt = dsRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), dsRows[0]?.pulled_at ?? '')

      const booneValueFor = (r: TradeValueLatestRow) =>
        r.position === 'QB' ? r.value_col1 : (scoring === 'ppr' ? r.value_col2 : r.value_col1)

      const blended = blendRosValues(
        dsRows.map(r => ({
          canonicalName: r.canonical_name, playerName: r.player_name, position: r.position,
          team: r.team, dsValue: r.ds_value, ceiling: r.ceiling_proj,
        })),
        booneRows.map(r => ({ canonicalName: r.canonical_name, position: r.position, value: booneValueFor(r) })),
      )

      let previousBlendedByName = new Map<string, number | null>()
      if (currentPulledAt) {
        const previous = await fetchPreviousRosSnapshot(scoring, currentPulledAt)
        if (previous) {
          const previousBlended = blendRosValues(
            previous.dsRows.map(r => ({
              canonicalName: r.canonical_name, playerName: r.player_name, position: r.position,
              team: r.team, dsValue: r.ds_value, ceiling: r.ceiling_proj,
            })),
            previous.booneRows.map(r => ({ canonicalName: r.canonical_name, position: r.position, value: booneValueFor(r) })),
          )
          previousBlendedByName = new Map(previousBlended.map(r => [r.canonicalName, r.blendedValue]))
        }
      }

      if (cancelled) return
      setRows(blended.map(r => {
        const prev = previousBlendedByName.get(r.canonicalName)
        const rosChange = r.blendedValue != null && prev != null ? r.blendedValue - prev : null
        return { ...r, rosChange }
      }))
      setFreshest(currentPulledAt || null)
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [scoring])

  return { rows, loading, error, freshest }
}

function useWeeklyTab(scoring: Scoring, week: number | null) {
  const [rows, setRows] = useState<AggregatedWeeklyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    if (week == null) return
    let cancelled = false
    setLoading(true)
    setError(null)

    supabase
      .from('in_season_rankings_latest')
      .select('*')
      .eq('scoring', scoring)
      .eq('week', week)
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) { setError(error.message); setLoading(false); return }

        const rankingRows = (data ?? []) as RankingLatestRow[]
        const byPlayer = new Map<string, RankingLatestRow[]>()
        rankingRows.forEach(r => {
          const list = byPlayer.get(r.canonical_name) ?? []
          list.push(r)
          byPlayer.set(r.canonical_name, list)
        })

        const players = Array.from(byPlayer.entries()).map(([canonicalName, sourceRows]) => {
          const ds = sourceRows.find(r => r.source === 'draftsharks')
          const boone = sourceRows.find(r => r.source === 'boone')
          const smythe = sourceRows.find(r => r.source === 'smythe')
          const any = ds ?? boone ?? smythe ?? sourceRows[0]
          return {
            canonicalName,
            playerName: any.player_name,
            position: any.position,
            team: any.team,
            draftsharksRank: ds?.rank ?? null,
            booneRank: boone?.rank ?? null,
            smytheRank: smythe?.rank ?? null,
            dsProjection: ds?.projection ?? null,
            dsFloor: ds?.floor_proj ?? null,
            dsCeiling: ds?.ceiling_proj ?? null,
            opponent: any.opponent,
          }
        })

        setRows(aggregateWeeklyRanks(players))
        setFreshest(rankingRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), rankingRows[0]?.pulled_at ?? '') || null)
        setLoading(false)
      })

    return () => { cancelled = true }
  }, [scoring, week])

  return { rows, loading, error, freshest }
}

export default function Rankings() {
  const [tab, setTab] = useState<'ros' | 'weekly'>('ros')
  const [pos, setPos] = useState('ALL')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [query, setQuery] = useState('')

  const { week, weeks } = useCurrentWeek()
  const ros = useRosTab(scoring)
  const weekly = useWeeklyTab(scoring, week)

  const active = tab === 'ros' ? ros : weekly

  const filteredRos = useMemo(() => {
    let list = ros.rows
    if (pos !== 'ALL') list = list.filter(r => r.position === pos)
    if (query) list = list.filter(r => r.playerName.toLowerCase().includes(query.toLowerCase()))
    return list
  }, [ros.rows, pos, query])

  const filteredWeekly = useMemo(() => {
    let list = weekly.rows
    if (pos !== 'ALL') list = list.filter(r => r.position === pos)
    if (query) list = list.filter(r => r.playerName.toLowerCase().includes(query.toLowerCase()))
    return list
  }, [weekly.rows, pos, query])

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button className={`btn ${tab === 'ros' ? 'btn-primary' : ''}`} onClick={() => setTab('ros')}>ROS</button>
        <button className={`btn ${tab === 'weekly' ? 'btn-primary' : ''}`} onClick={() => setTab('weekly')}>Weekly</button>
      </div>

      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <input className="input" placeholder="Search players..." value={query} onChange={e => setQuery(e.target.value)} />
          <select className="input" value={pos} onChange={e => setPos(e.target.value)}>
            {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="input" value={scoring} onChange={e => setScoring(e.target.value as Scoring)}>
            {SCORINGS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {tab === 'weekly' && (
            <select className="input" value={week ?? ''} onChange={() => {}} disabled>
              <option value={week ?? ''}>Week {week ?? '…'}</option>
            </select>
          )}
          {active.freshest && <span className="subtle ml-auto">Data as of {new Date(active.freshest).toLocaleString()}</span>}
        </div>

        {active.loading && <div className="subtle">Loading…</div>}
        {active.error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {active.error}</div>}

        {!active.loading && !active.error && tab === 'ros' && (
          <table className="table">
            <thead>
              <tr>
                <th>Rank</th><th>Player</th><th>Pos</th><th>Team</th>
                <th>Blended</th><th>DS Value</th><th>Boone Value</th><th>DS Ceiling</th><th>ROS Δ</th>
              </tr>
            </thead>
            <tbody>
              {filteredRos.map(r => (
                <tr key={r.canonicalName}>
                  <td>{r.overallRank ?? ''}</td>
                  <td>{r.playerName}</td>
                  <td>{r.position}</td>
                  <td>{r.team ?? ''}</td>
                  <td className="text-right font-semibold">{r.blendedValue != null ? Math.round(r.blendedValue) : ''}</td>
                  <td className="text-right">{r.dsValue ?? ''}</td>
                  <td className="text-right">{r.booneValue ?? ''}</td>
                  <td className="text-right">{r.ceiling ?? ''}</td>
                  <td className="text-right">
                    {r.rosChange == null
                      ? <span className="subtle">New</span>
                      : <span className={r.rosChange >= 0 ? 'signal-up' : 'signal-down'}>{r.rosChange >= 0 ? '+' : ''}{Math.round(r.rosChange)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!active.loading && !active.error && tab === 'weekly' && (
          <table className="table">
            <thead>
              <tr>
                <th>Agg. Rank</th><th>Player</th><th>Pos</th><th>Team</th>
                <th>DS Rank</th><th>Boone Rank</th><th>DS Proj</th><th>Floor</th><th>Ceiling</th><th>Opp</th>
              </tr>
            </thead>
            <tbody>
              {filteredWeekly.map(r => (
                <tr key={r.canonicalName}>
                  <td>{r.aggregateRank ?? ''}</td>
                  <td>{r.playerName}</td>
                  <td>{r.position}</td>
                  <td>{r.team ?? ''}</td>
                  <td className="text-right">{r.draftsharksRank ?? ''}</td>
                  <td className="text-right">{r.booneRank ?? ''}</td>
                  <td className="text-right">{r.dsProjection ?? ''}</td>
                  <td className="text-right">{r.dsFloor ?? ''}</td>
                  <td className="text-right">{r.dsCeiling ?? ''}</td>
                  <td>{r.opponent ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!active.loading && !active.error && (tab === 'ros' ? filteredRos : filteredWeekly).length === 0 && (
          <div className="subtle">No rows match these filters.</div>
        )}
      </div>
    </div>
  )
}
