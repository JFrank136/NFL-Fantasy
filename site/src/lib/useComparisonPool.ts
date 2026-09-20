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
import { buildComparisonPool, type ComparisonPlayer } from './playerComparison'

export interface ComparisonPoolResult {
  pool: ComparisonPlayer[]
  freshest: string
  loading: boolean
  error: string | null
}

export function useComparisonPool(scoring: Scoring): ComparisonPoolResult {
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

  return { pool, freshest, loading, error }
}
