import { useEffect, useMemo, useState } from 'react'
import { supabase, type RankingLatestRow, type RosRankingRow, type TradeValueLatestRow } from '../lib/supabase'
import { blendRosValues, aggregateWeeklyRanks, type BlendedRosRow, type AggregatedWeeklyRow } from '../lib/blend'
import { fetchPreviousRosSnapshot } from '../lib/rosHistory'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
type Scoring = typeof SCORINGS[number]

type RosTabRow = BlendedRosRow & { rosChange: number | null }

type SortDir = 'asc' | 'desc'
type ColumnType = 'string' | 'number'

interface ColumnDef<T> {
  key: keyof T & string
  label: string
  type: ColumnType
}

interface SortState {
  key: string | null
  dir: SortDir
}

function toggleSort(prev: SortState, key: string): SortState {
  if (prev.key === key) return { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
  return { key, dir: 'asc' }
}

function sortRows<T>(
  rows: T[],
  columns: ColumnDef<T>[],
  sort: SortState,
): T[] {
  if (!sort.key) return rows
  const column = columns.find(c => c.key === sort.key)
  if (!column) return rows
  const dirMul = sort.dir === 'asc' ? 1 : -1

  return [...rows].sort((a, b) => {
    const av = a[column.key] as unknown
    const bv = b[column.key] as unknown

    if (column.type === 'number') {
      const an = av as number | null
      const bn = bv as number | null
      if (an == null && bn == null) return 0
      if (an == null) return 1
      if (bn == null) return -1
      return (an - bn) * dirMul
    }

    const as = ((av as string | null) ?? '').toLowerCase()
    const bs = ((bv as string | null) ?? '').toLowerCase()
    if (as < bs) return -1 * dirMul
    if (as > bs) return 1 * dirMul
    return 0
  })
}

function SortableHeader({ label, columnKey, sort, onSort }: { label: string; columnKey: string; sort: SortState; onSort: (key: string) => void }) {
  const active = sort.key === columnKey
  return (
    <th className="sortable" onClick={() => onSort(columnKey)}>
      {label}
      {active && <span className="sort-indicator">{sort.dir === 'asc' ? ' ▲' : ' ▼'}</span>}
    </th>
  )
}

const ROS_COLUMNS: ColumnDef<RosTabRow>[] = [
  { key: 'overallRank', label: 'Rank', type: 'number' },
  { key: 'playerName', label: 'Player', type: 'string' },
  { key: 'position', label: 'Pos', type: 'string' },
  { key: 'team', label: 'Team', type: 'string' },
  { key: 'blendedValue', label: 'Blended', type: 'number' },
  { key: 'dsValue', label: 'DS Value', type: 'number' },
  { key: 'booneValue', label: 'Boone Value', type: 'number' },
  { key: 'ceiling', label: 'DS Ceiling', type: 'number' },
  { key: 'rosChange', label: 'ROS Δ', type: 'number' },
]

const WEEKLY_COLUMNS: ColumnDef<AggregatedWeeklyRow>[] = [
  { key: 'aggregateRank', label: 'Agg. Rank', type: 'number' },
  { key: 'playerName', label: 'Player', type: 'string' },
  { key: 'position', label: 'Pos', type: 'string' },
  { key: 'team', label: 'Team', type: 'string' },
  { key: 'draftsharksRank', label: 'DS Rank', type: 'number' },
  { key: 'booneRank', label: 'Boone Rank', type: 'number' },
  { key: 'dsProjection', label: 'DS Proj', type: 'number' },
  { key: 'dsFloor', label: 'Floor', type: 'number' },
  { key: 'dsCeiling', label: 'Ceiling', type: 'number' },
  { key: 'opponent', label: 'Opp', type: 'string' },
]

function useCurrentWeek() {
  const [week, setWeek] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    supabase
      .from('in_season_rankings_latest')
      .select('week')
      .in('source', ['boone', 'smythe'])
      .order('week', { ascending: false })
      .limit(1)
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) {
          console.error('Failed to fetch current week:', error)
          setError(error.message)
          return
        }
        setWeek(data?.[0]?.week ?? null)
      })
    return () => { cancelled = true }
  }, [])

  return { week, error }
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

function useWeeklyTab(scoring: Scoring, week: number | null, weekError: string | null) {
  const [rows, setRows] = useState<AggregatedWeeklyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    if (week == null) {
      if (weekError) {
        setError(weekError)
        setLoading(false)
      }
      return
    }
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
  }, [scoring, week, weekError])

  return { rows, loading, error, freshest }
}

export default function Rankings() {
  const [tab, setTab] = useState<'ros' | 'weekly'>('ros')
  const [pos, setPos] = useState('ALL')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [query, setQuery] = useState('')

  const { week, error: weekError } = useCurrentWeek()
  const [rosSort, setRosSort] = useState<SortState>({ key: null, dir: 'asc' })
  const [weeklySort, setWeeklySort] = useState<SortState>({ key: null, dir: 'asc' })
  const ros = useRosTab(scoring)
  const weekly = useWeeklyTab(scoring, week, weekError)

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

  const sortedRos = useMemo(() => sortRows(filteredRos, ROS_COLUMNS, rosSort), [filteredRos, rosSort])
  const sortedWeekly = useMemo(() => sortRows(filteredWeekly, WEEKLY_COLUMNS, weeklySort), [filteredWeekly, weeklySort])

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
                {ROS_COLUMNS.map(col => (
                  <SortableHeader
                    key={col.key}
                    label={col.label}
                    columnKey={col.key}
                    sort={rosSort}
                    onSort={key => setRosSort(prev => toggleSort(prev, key))}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRos.map(r => (
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
                {WEEKLY_COLUMNS.map(col => (
                  <SortableHeader
                    key={col.key}
                    label={col.label}
                    columnKey={col.key}
                    sort={weeklySort}
                    onSort={key => setWeeklySort(prev => toggleSort(prev, key))}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedWeekly.map(r => (
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

        {!active.loading && !active.error && (tab === 'ros' ? sortedRos : sortedWeekly).length === 0 && (
          <div className="subtle">No rows match these filters.</div>
        )}
      </div>
    </div>
  )
}
