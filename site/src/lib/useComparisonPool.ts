// src/lib/useComparisonPool.ts
//
// Shared "selectable ROS players" pool: blended ROS value, ceiling, trend
// and SOS per player. Extracted from Player Comparison so Add/Drop and
// Start/Sit reuse the exact same pool.

import { useMemo } from 'react'
import { useRosHistory } from './useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from './useBlendedRos'
import { blendRosValues, identityKey } from './blend'
import { buildMovers, splitSnapshots, TIMEFRAME_MIN_GAP_MS } from './movers'
import { onlyWeek } from './freshness'
import { useCurrentWeek } from './useCurrentWeek'
import { buildComparisonPool, type ComparisonPlayer } from './playerComparison'

export interface ComparisonPoolResult {
  pool: ComparisonPlayer[]
  freshest: string
  loading: boolean
  error: string | null
  /** True once Boone has data in but none of it is tagged for the current
   * week yet -- pool values fall back to Draft Sharks alone until Boone
   * re-pulls, rather than silently blending in last week's numbers. */
  boonePending: boolean
  currentWeek: number | null
}

export function useComparisonPool(scoring: Scoring): ComparisonPoolResult {
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)
  const { week: currentWeek } = useCurrentWeek()

  const { pool, freshest, boonePending } = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS.latest
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    // A source's own newest pull can still be a stale week if it hasn't
    // refreshed since the NFL week turned over -- gate "current" to this
    // week's data so a lagging source drops out instead of blending in.
    const dsCurrentRows = onlyWeek(ds.current, currentWeek, r => r.as_of_week)
    const booneCurrentRows = onlyWeek(boone.current, currentWeek, r => r.week)
    const current = { ds: dsCurrentRows.map(toDsRosInput), boone: booneCurrentRows.map(r => toBooneRosInput(r, scoring)) }

    const { rows: movers } = buildMovers('blended', current, {
      ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
      boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
    })
    const trendByKey = new Map(movers.map(m => [identityKey(m.canonicalName, m.position), m.change]))
    const sosByKey = new Map(dsCurrentRows.map(r => [identityKey(r.canonical_name, r.position), r.strength_of_schedule]))

    return {
      pool: buildComparisonPool(blendRosValues(current.ds, current.boone), trendByKey, sosByKey),
      freshest: dsCurrentRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
      boonePending: currentWeek != null && boone.current.length > 0 && booneCurrentRows.length === 0,
    }
  }, [dsRows, booneRows, scoring, currentWeek])

  return { pool, freshest, loading, error, boonePending, currentWeek }
}
