// src/lib/useBlendedRos.ts
//
// Shared "current blended ROS value" fetch -- Draft Sharks ROS rows +
// Boone trade-value rows, run through blendRosValues (blend.ts). Extracted
// out of Rankings' ROS tab so Trade Analyzer (and later Player Comparison,
// Add/Drop) can reuse the exact same fetch+blend instead of re-deriving it
// per page, per the roadmap's "reuse shared comparison logic" principle.

import { useEffect, useState } from 'react'
import { supabase, type RosRankingRow, type TradeValueLatestRow } from './supabase'
import { blendRosValues, type BlendedRosRow, type RosSourceRow, type BooneRosRow } from './blend'

export type Scoring = 'ppr' | 'half-ppr'

/** Boone's trade-value sheet has no QB scoring split (only one column
 * matters for QBs); RB/WR/TE use value_col2 for PPR, value_col1 for
 * half-PPR, matching how Rankings' ROS tab already reads this table. */
export function booneRosValueFor(r: TradeValueLatestRow, scoring: Scoring): number | null {
  return r.position === 'QB' ? r.value_col1 : (scoring === 'ppr' ? r.value_col2 : r.value_col1)
}

export function toDsRosInput(r: RosRankingRow): RosSourceRow {
  return {
    canonicalName: r.canonical_name, playerName: r.player_name, position: r.position,
    team: r.team, dsValue: r.ds_value, ceiling: r.ceiling_proj,
  }
}

export function toBooneRosInput(r: TradeValueLatestRow, scoring: Scoring): BooneRosRow {
  return { canonicalName: r.canonical_name, position: r.position, value: booneRosValueFor(r, scoring) }
}

export interface BlendedRosResult {
  rows: BlendedRosRow[]
  loading: boolean
  error: string | null
  freshest: string | null
}

export function useBlendedRos(scoring: Scoring): BlendedRosResult {
  const [rows, setRows] = useState<BlendedRosRow[]>([])
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
    ]).then(([dsRes, booneRes]) => {
      if (cancelled) return
      if (dsRes.error) { setError(dsRes.error.message); setLoading(false); return }
      if (booneRes.error) { setError(booneRes.error.message); setLoading(false); return }

      const dsRows = (dsRes.data ?? []) as RosRankingRow[]
      const booneRows = (booneRes.data ?? []) as TradeValueLatestRow[]
      const currentPulledAt = dsRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), dsRows[0]?.pulled_at ?? '')

      const blended = blendRosValues(
        dsRows.map(toDsRosInput),
        booneRows.map(r => toBooneRosInput(r, scoring)),
      )

      setRows(blended)
      setFreshest(currentPulledAt || null)
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [scoring])

  return { rows, loading, error, freshest }
}
