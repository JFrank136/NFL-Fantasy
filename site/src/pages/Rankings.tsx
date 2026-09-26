import { useMemo, useState } from 'react'
import { blendRosValues, identityKey, type BlendedRosRow, type AggregatedWeeklyRow } from '../lib/blend'
import { useRosHistory } from '../lib/useRosHistory'
import { useWeeklyRows } from '../lib/useWeeklyRows'
import { toBooneRosInput, toDsRosInput } from '../lib/useBlendedRos'
import { buildMovers, splitSnapshots, TIMEFRAME_MIN_GAP_MS } from '../lib/movers'
import { onlyWeek } from '../lib/freshness'
import { useCurrentWeek } from '../lib/useCurrentWeek'
import { computeFlexRanks, FLEX_POSITIONS } from '../lib/weeklyPool'
import ColumnPicker, { toggleInSet } from '../components/ColumnPicker'

// Weekly has no 'ALL' -- aggregateWeeklyRanks ranks within each position, so
// an "ALL" view would just interleave separate position-scoped #1's (the
// exact "multiple 1's" confusion this page exists to avoid), and it's the
// only way K/DST sneak into a view nobody asked to see them in. FLEX is the
// cross-position view weekly does support: RB/WR/TE share one score scale
// (see weeklyPool.ts). ROS keeps 'ALL' since blendRosValues computes one
// genuine cross-position rank.
const WEEKLY_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'FLEX']
const ROS_POSITIONS = ['ALL', ...WEEKLY_POSITIONS]
const matchesPosition = (pos: string, rowPos: string) =>
  pos === 'ALL' || (pos === 'FLEX' ? FLEX_POSITIONS.includes(rowPos) : rowPos === pos)
const SCORINGS = ['ppr', 'half-ppr'] as const
type Scoring = typeof SCORINGS[number]
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

type RosTabRow = BlendedRosRow & { rosChange: number | null }
/** Rank within the position filter currently applied (overall when ALL). */
type RosDisplayRow = RosTabRow & { displayRank: number | null }
/** aggregateRank is per position; displayRank is FLEX rank on the FLEX view. */
type WeeklyDisplayRow = AggregatedWeeklyRow & { displayRank: number | null }

type SortDir = 'asc' | 'desc'
type ColumnType = 'string' | 'number'

interface ColumnDef<T> {
  key: keyof T & string
  label: string
  type: ColumnType
  /** Right-aligned numeric columns: header aligns the same way as its values. */
  right?: boolean
  /** Can't be hidden from the column picker. */
  required?: boolean
  sticky?: boolean
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

function SortableHeader({ label, columnKey, sort, onSort, right, sticky }: { label: string; columnKey: string; sort: SortState; onSort: (key: string) => void; right?: boolean; sticky?: boolean }) {
  const active = sort.key === columnKey
  return (
    <th className={`sortable${right ? ' num' : ''}${sticky ? ' sticky-col' : ''}`} onClick={() => onSort(columnKey)}>
      {label}
      {active && <span className="sort-indicator">{sort.dir === 'asc' ? ' ▲' : ' ▼'}</span>}
    </th>
  )
}

const ROS_COLUMNS: ColumnDef<RosDisplayRow>[] = [
  { key: 'displayRank', label: 'Rank', type: 'number', required: true },
  { key: 'overallRank', label: 'Overall', type: 'number' },
  { key: 'playerName', label: 'Player', type: 'string', required: true, sticky: true },
  { key: 'position', label: 'Pos', type: 'string' },
  { key: 'team', label: 'Team', type: 'string' },
  { key: 'blendedValue', label: 'Blended', type: 'number', right: true },
  { key: 'dsValue', label: 'DS Value', type: 'number', right: true },
  { key: 'booneValue', label: 'Boone Value', type: 'number', right: true },
  { key: 'ceiling', label: 'DS Ceiling', type: 'number', right: true },
  { key: 'rosChange', label: 'ROS Δ', type: 'number', right: true },
]

const WEEKLY_COLUMNS: ColumnDef<WeeklyDisplayRow>[] = [
  { key: 'displayRank', label: 'Rank', type: 'number', required: true },
  { key: 'aggregateRank', label: 'Pos Rank', type: 'number' },
  { key: 'playerName', label: 'Player', type: 'string', required: true, sticky: true },
  { key: 'position', label: 'Pos', type: 'string' },
  { key: 'team', label: 'Team', type: 'string' },
  { key: 'opponent', label: 'Opp', type: 'string' },
  { key: 'draftsharksRank', label: 'DS Rank', type: 'number', right: true },
  { key: 'booneRank', label: 'Boone Rank', type: 'number', right: true },
  { key: 'dsFloor', label: 'Floor', type: 'number', right: true },
  { key: 'dsProjection', label: 'DS Proj', type: 'number', right: true },
  { key: 'dsCeiling', label: 'Ceiling', type: 'number', right: true },
]

function useRosTab(scoring: Scoring) {
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)
  const { week: currentWeek } = useCurrentWeek()

  const { rows, freshest, boonePending } = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS.latest
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    // A source's own newest pull can still be a stale week if it hasn't
    // refreshed since the NFL week turned over -- gate "current" to this
    // week's data so a lagging source drops out instead of blending in.
    const dsCurrentRows = onlyWeek(ds.current, currentWeek, r => r.as_of_week)
    const booneCurrentRows = onlyWeek(boone.current, currentWeek, r => r.week)
    const current = { ds: dsCurrentRows.map(toDsRosInput), boone: booneCurrentRows.map(r => toBooneRosInput(r, scoring)) }

    // Same per-position baseline as Movers & Fallers, so ROS Δ here and the
    // "Latest change" there always agree.
    const { rows: movers } = buildMovers('blended', current, {
      ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
      boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
    })
    const changeByKey = new Map(movers.map(m => [identityKey(m.canonicalName, m.position), m.change]))

    const tabRows: RosTabRow[] = blendRosValues(current.ds, current.boone).map(r => ({
      ...r,
      rosChange: changeByKey.get(identityKey(r.canonicalName, r.position)) ?? null,
    }))
    const newest = dsCurrentRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), '')
    return {
      rows: tabRows,
      freshest: newest || null,
      boonePending: currentWeek != null && boone.current.length > 0 && booneCurrentRows.length === 0,
    }
  }, [dsRows, booneRows, scoring, currentWeek])

  return { rows, loading, error, freshest, boonePending, currentWeek }
}

export default function Rankings() {
  const [tab, setTab] = useState<'ros' | 'weekly'>('weekly')
  const [pos, setPos] = useState('QB')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [query, setQuery] = useState('')
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set())

  const [rosSort, setRosSort] = useState<SortState>({ key: 'displayRank', dir: 'asc' })
  const [weeklySort, setWeeklySort] = useState<SortState>({ key: 'displayRank', dir: 'asc' })
  const ros = useRosTab(scoring)
  const weekly = useWeeklyRows(scoring)
  const week = weekly.week

  const active = tab === 'ros' ? ros : weekly
  const positions = tab === 'ros' ? ROS_POSITIONS : WEEKLY_POSITIONS

  const goToWeekly = () => {
    setTab('weekly')
    setWeeklySort({ key: 'displayRank', dir: 'asc' })
    if (pos === 'ALL') setPos('QB')
  }

  // Ranks are assigned within the position filter BEFORE the search box
  // narrows things, so searching for one player still shows their real rank.
  const rankedRos = useMemo<RosDisplayRow[]>(() => {
    const scoped = ros.rows.filter(r => matchesPosition(pos, r.position))
    if (pos === 'ALL') return scoped.map(r => ({ ...r, displayRank: r.overallRank }))
    const ordered = [...scoped].sort((a, b) => (a.overallRank ?? Infinity) - (b.overallRank ?? Infinity))
    return ordered.map((r, i) => ({ ...r, displayRank: r.overallRank == null ? null : i + 1 }))
  }, [ros.rows, pos])

  const rankedWeekly = useMemo<WeeklyDisplayRow[]>(() => {
    const scoped = weekly.rows.filter(r => matchesPosition(pos, r.position))
    if (pos !== 'FLEX') return scoped.map(r => ({ ...r, displayRank: r.aggregateRank }))
    const flex = computeFlexRanks(scoped, week)
    return scoped.map(r => ({ ...r, displayRank: flex.get(identityKey(r.canonicalName, r.position)) ?? null }))
  }, [weekly.rows, pos, week])

  const matchesQuery = (name: string) => !query || name.toLowerCase().includes(query.toLowerCase())
  const sortedRos = useMemo(
    () => sortRows(rankedRos.filter(r => matchesQuery(r.playerName)), ROS_COLUMNS, rosSort),
    [rankedRos, query, rosSort],
  )
  const sortedWeekly = useMemo(
    () => sortRows(rankedWeekly.filter(r => matchesQuery(r.playerName)), WEEKLY_COLUMNS, weeklySort),
    [rankedWeekly, query, weeklySort],
  )

  // Overall rank only adds something once the main rank is scoped to a
  // position; Pos Rank only once weekly is showing the cross-position FLEX list.
  const rosCols = ROS_COLUMNS.filter(c => !(c.key === 'overallRank' && pos === 'ALL') && !hiddenCols.has(c.key))
  const weeklyCols = WEEKLY_COLUMNS.filter(c => !(c.key === 'aggregateRank' && pos !== 'FLEX') && !hiddenCols.has(c.key))
  const rankLabel = pos === 'ALL' ? 'Rank' : `${pos} Rank`
  const labelFor = (key: string, label: string) => (key === 'displayRank' ? rankLabel : label)
  const pickable = (tab === 'ros' ? ROS_COLUMNS : WEEKLY_COLUMNS)
    .filter(c => !c.required && !(c.key === 'overallRank' && pos === 'ALL') && !(c.key === 'aggregateRank' && pos !== 'FLEX'))
    .map(c => ({ key: c.key as string, label: c.label }))

  const rosCell = (r: RosDisplayRow, key: string) => {
    switch (key) {
      case 'displayRank': return r.displayRank ?? ''
      case 'overallRank': return r.overallRank ?? ''
      case 'playerName': return r.playerName
      case 'position': return r.position
      case 'team': return r.team ?? ''
      case 'blendedValue': return r.blendedValue != null ? Math.round(r.blendedValue) : ''
      case 'dsValue': return r.dsValue ?? ''
      case 'booneValue': return r.booneValue ?? ''
      case 'ceiling': return r.ceiling ?? ''
      default:
        return r.rosChange == null
          ? <span className="subtle">New</span>
          : <span className={r.rosChange >= 0 ? 'signal-up' : 'signal-down'}>{r.rosChange >= 0 ? '+' : ''}{Math.round(r.rosChange)}</span>
    }
  }

  const weeklyCell = (r: WeeklyDisplayRow, key: string) => {
    switch (key) {
      case 'displayRank': return r.displayRank ?? ''
      case 'aggregateRank': return r.aggregateRank ?? ''
      case 'playerName': return r.playerName
      case 'position': return r.position
      case 'team': return r.team ?? ''
      case 'opponent': return r.opponent ?? ''
      case 'draftsharksRank': return r.draftsharksRank ?? ''
      case 'booneRank': return r.booneRank ?? ''
      case 'dsFloor': return r.dsFloor ?? ''
      case 'dsProjection': return r.dsProjection ?? ''
      default: return r.dsCeiling ?? ''
    }
  }

  const cellClass = (c: { right?: boolean; sticky?: boolean; key: string }) =>
    [c.right ? 'text-right' : '', c.sticky ? 'sticky-col' : '', c.key === 'blendedValue' ? 'font-semibold' : ''].filter(Boolean).join(' ') || undefined

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button className={`btn ${tab === 'weekly' ? 'btn-primary' : ''}`} onClick={goToWeekly}>Weekly</button>
        <button className={`btn ${tab === 'ros' ? 'btn-primary' : ''}`} onClick={() => setTab('ros')}>ROS</button>
      </div>

      <div className="card p-3 sm:p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <input className="input w-full sm:w-auto" placeholder="Search players..." value={query} onChange={e => setQuery(e.target.value)} />
          <div className="flex gap-1 flex-wrap">
            {positions.map(p => (
              <button
                key={p}
                className={`btn ${pos === p ? 'btn-primary' : ''}`}
                onClick={() => setPos(p)}
              >
                {p}
              </button>
            ))}
          </div>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {tab === 'weekly' && (
            <span className="btn btn-primary" style={{ cursor: 'default' }}>Week {week ?? '…'}</span>
          )}
          {active.freshest && <span className="subtle sm:ml-auto">Data as of {new Date(active.freshest).toLocaleString()}</span>}
        </div>

        <ColumnPicker columns={pickable} hidden={hiddenCols} onToggle={key => setHiddenCols(prev => toggleInSet(prev, key))} />

        {active.loading && <div className="subtle">Loading…</div>}
        {active.error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {active.error}</div>}
        {tab === 'ros' && !ros.loading && !ros.error && ros.boonePending && (
          <div className="subtle">Boone hasn't updated ROS values for Week {ros.currentWeek} yet -- Boone Value/Blended below are Draft Sharks only until it does.</div>
        )}

        {!active.loading && !active.error && tab === 'ros' && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {rosCols.map(col => (
                    <SortableHeader
                      key={col.key}
                      label={labelFor(col.key, col.label)}
                      columnKey={col.key}
                      sort={rosSort}
                      right={col.right}
                      sticky={col.sticky}
                      onSort={key => setRosSort(prev => toggleSort(prev, key))}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRos.map(r => (
                  <tr key={identityKey(r.canonicalName, r.position)}>
                    {rosCols.map(col => <td key={col.key} className={cellClass(col)}>{rosCell(r, col.key)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!active.loading && !active.error && tab === 'weekly' && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {weeklyCols.map(col => (
                    <SortableHeader
                      key={col.key}
                      label={labelFor(col.key, col.label)}
                      columnKey={col.key}
                      sort={weeklySort}
                      right={col.right}
                      sticky={col.sticky}
                      onSort={key => setWeeklySort(prev => toggleSort(prev, key))}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedWeekly.map(r => (
                  <tr key={identityKey(r.canonicalName, r.position)}>
                    {weeklyCols.map(col => <td key={col.key} className={cellClass(col)}>{weeklyCell(r, col.key)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!active.loading && !active.error && (tab === 'ros' ? sortedRos : sortedWeekly).length === 0 && (
          <div className="subtle">No rows match these filters.</div>
        )}
      </div>
    </div>
  )
}
