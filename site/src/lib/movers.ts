// src/lib/movers.ts
//
// Pure calculation functions for the Movers & Fallers page. No Supabase, no
// React. Compares each player's current value against a baseline snapshot
// and ranks the biggest value changes (value movement, not rank movement --
// a small rank change can be a large or tiny real value change).

import { blendRosValues, identityKey, type BlendedRosRow, type RosSourceRow, type BooneRosRow } from './blend'

export type Metric = 'blended' | 'boone' | 'booneScaled' | 'ds' | 'ceiling'
export type Timeframe = 'latest' | 'week'

const HOUR_MS = 60 * 60 * 1000

/** Minimum age of the baseline snapshot relative to the current one.
 * "Latest change" still requires an hour so back-to-back reruns of the same
 * scrape (which happen) don't become a baseline that shows ~zero movement.
 * Configurable/tunable, per the roadmap. */
export const TIMEFRAME_MIN_GAP_MS: Record<Timeframe, number> = {
  latest: HOUR_MS,
  week: 7 * 24 * HOUR_MS,
}

interface Snapshotted {
  pulled_at: string
  position: string
}

export interface SnapshotSplit<T> {
  current: T[]
  baseline: T[]
  /** pulled_at of the baseline for each position that has one. */
  baselineTimes: string[]
}

/**
 * Splits an append-only history into the current snapshot and a baseline,
 * independently per position: sources scrape per position and occasionally
 * rerun a single position, so positions don't always share one pulled_at.
 * Current = each position's newest pull; baseline = that position's newest
 * pull at least minGapMs older than its current one (empty if none).
 */
export function splitSnapshots<T extends Snapshotted>(rows: T[], minGapMs: number): SnapshotSplit<T> {
  const byPosition = new Map<string, Map<string, T[]>>()
  for (const row of rows) {
    const byTime = byPosition.get(row.position) ?? new Map<string, T[]>()
    const list = byTime.get(row.pulled_at) ?? []
    list.push(row)
    byTime.set(row.pulled_at, list)
    byPosition.set(row.position, byTime)
  }

  const current: T[] = []
  const baseline: T[] = []
  const baselineTimes: string[] = []

  byPosition.forEach(byTime => {
    const times = Array.from(byTime.keys()).sort((a, b) => Date.parse(b) - Date.parse(a))
    const currentTime = times[0]
    current.push(...byTime.get(currentTime)!)

    const cutoff = Date.parse(currentTime) - minGapMs
    const baselineTime = times.find(t => Date.parse(t) <= cutoff)
    if (baselineTime) {
      baseline.push(...byTime.get(baselineTime)!)
      baselineTimes.push(baselineTime)
    }
  })

  return { current, baseline, baselineTimes }
}

/**
 * Picks, per position, the most recent pull tagged with the given NFL week
 * -- "Since last week" wants the latest snapshot actually FROM last week,
 * not just any pull that happens to be old enough by wall-clock time
 * (that's what "Latest change" already does via splitSnapshots' minGapMs
 * cutoff, and stays duration-based on purpose: it's about the most recent
 * real change, not a specific week).
 */
export function weekSnapshot<T extends Snapshotted>(
  rows: T[],
  week: number | null,
  weekOf: (row: T) => number,
): { rows: T[]; times: string[] } {
  if (week == null) return { rows: [], times: [] }

  const byPosition = new Map<string, T[]>()
  rows.forEach(row => {
    if (weekOf(row) !== week) return
    const list = byPosition.get(row.position) ?? []
    list.push(row)
    byPosition.set(row.position, list)
  })

  const result: T[] = []
  const times: string[] = []
  byPosition.forEach(list => {
    const newest = list.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), list[0].pulled_at)
    result.push(...list.filter(r => r.pulled_at === newest))
    times.push(newest)
  })
  return { rows: result, times }
}

/** "Draft Sharks: vs. 9/13/2026-9/18/2026" -- which snapshots a change is measured against. */
export function describeBaseline(label: string, times: string[]): string {
  if (times.length === 0) return `${label}: no baseline yet`
  const sorted = [...times].sort((a, b) => Date.parse(a) - Date.parse(b))
  const first = new Date(sorted[0]).toLocaleDateString()
  const last = new Date(sorted[sorted.length - 1]).toLocaleDateString()
  return `${label}: vs. ${first === last ? first : `${first}–${last}`}`
}

/** Why a source has no baseline yet for this timeframe -- how far back its
 * pull history actually goes vs. how old a baseline this timeframe needs,
 * so "not enough history" reads as a concrete, dated explanation (e.g.
 * Draft Sharks pull history starting 9/18 genuinely can't have a 7-day-old
 * "since last week" baseline until 9/25) instead of a generic message. */
export function explainMissingBaseline(label: string, rows: { pulled_at: string }[], minGapMs: number): string {
  if (rows.length === 0) return `${label}: no pulls yet`
  const earliest = rows.reduce((min, r) => (r.pulled_at < min ? r.pulled_at : min), rows[0].pulled_at)
  const readyAt = new Date(Date.parse(earliest) + minGapMs)
  return `${label}: pull history only goes back to ${new Date(earliest).toLocaleDateString()} -- check back after ${readyAt.toLocaleDateString()}`
}

/** Why a source has no "since last week" baseline: it simply has no data
 * tagged with the previous NFL week yet (as opposed to "Latest change",
 * which is a wall-clock-age question -- see explainMissingBaseline). */
export function explainMissingWeekBaseline(label: string, previousWeek: number | null): string {
  if (previousWeek == null) return `${label}: no previous week yet`
  return `${label}: no Week ${previousWeek} data yet`
}

export interface SourceInputs {
  ds: RosSourceRow[]
  boone: BooneRosRow[]
}

/** null = that source has no baseline snapshot for the chosen timeframe. */
export interface BaselineInputs {
  ds: RosSourceRow[] | null
  boone: BooneRosRow[] | null
}

export interface MoverRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  current: number | null
  previous: number | null
  change: number | null
  /** Rank by current value across all positions, before any filtering. */
  rank: number | null
}

export interface MoversResult {
  rows: MoverRow[]
  /** False when the chosen metric's source(s) have no baseline yet. */
  baselineAvailable: boolean
}

function valueOf(row: BlendedRosRow, metric: Metric): number | null {
  switch (metric) {
    case 'blended': return row.blendedValue
    case 'boone': return row.booneValue
    case 'booneScaled': return row.booneScaled
    case 'ds': return row.dsValue
    case 'ceiling': return row.ceiling
  }
}

/** Which raw sources a metric is derived from -- 'blended'/'booneScaled'
 * need both (scaling Boone onto the DS scale needs both baselines, same as
 * the blend); everything else needs just its own source. Used both to gate
 * baseline availability and to explain, per source, why one is missing. */
export function metricSources(metric: Metric): ('ds' | 'boone')[] {
  switch (metric) {
    case 'blended':
    case 'booneScaled': return ['ds', 'boone']
    case 'boone': return ['boone']
    case 'ds':
    case 'ceiling': return ['ds']
  }
}

function baselineAvailableFor(metric: Metric, base: BaselineInputs): boolean {
  return metricSources(metric).every(source => base[source] != null)
}

export function buildMovers(metric: Metric, current: SourceInputs, baseline: BaselineInputs): MoversResult {
  const currentRows = blendRosValues(current.ds, current.boone)
  const baselineAvailable = baselineAvailableFor(metric, baseline)

  const previousByKey = new Map<string, number | null>()
  if (baselineAvailable) {
    blendRosValues(baseline.ds ?? [], baseline.boone ?? []).forEach(r => {
      previousByKey.set(identityKey(r.canonicalName, r.position), valueOf(r, metric))
    })
  }

  const rows: MoverRow[] = currentRows.map(r => {
    const currentValue = valueOf(r, metric)
    const previous = previousByKey.get(identityKey(r.canonicalName, r.position)) ?? null
    return {
      canonicalName: r.canonicalName,
      playerName: r.playerName,
      position: r.position,
      team: r.team,
      current: currentValue,
      previous,
      change: currentValue != null && previous != null ? currentValue - previous : null,
      rank: null,
    }
  })

  const ranked = rows
    .filter(r => r.current != null)
    .sort((a, b) => (b.current as number) - (a.current as number))
  ranked.forEach((r, i) => { r.rank = i + 1 })

  return { rows, baselineAvailable }
}

/** Largest positive / negative changes. Unchanged players are excluded. */
export function topMovers(rows: MoverRow[], limit: number): { risers: MoverRow[]; fallers: MoverRow[] } {
  const changed = rows.filter((r): r is MoverRow & { change: number } => r.change != null && r.change !== 0)
  const risers = changed.filter(r => r.change > 0).sort((a, b) => b.change - a.change).slice(0, limit)
  const fallers = changed.filter(r => r.change < 0).sort((a, b) => a.change - b.change).slice(0, limit)
  return { risers, fallers }
}
