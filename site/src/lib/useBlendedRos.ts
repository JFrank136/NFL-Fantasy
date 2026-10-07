// src/lib/useBlendedRos.ts
//
// Shared "current blended ROS value" fetch -- Draft Sharks ROS rows +
// Boone trade-value rows, run through blendRosValues (blend.ts). Extracted
// out of Rankings' ROS tab so Trade Analyzer (and later Player Comparison,
// Add/Drop) can reuse the exact same fetch+blend instead of re-deriving it
// per page, per the roadmap's "reuse shared comparison logic" principle.

import { useEffect, useState } from 'react'
import { supabase, fetchAllRows, type RosRankingRow, type TradeValueLatestRow } from './supabase'
import { blendRosValues, type BlendedRosRow, type RosSourceRow, type BooneRosRow } from './blend'
import { dropStaleStragglers, onlyWeek } from './freshness'
import { useCurrentWeek } from './useCurrentWeek'

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
  /** True once Boone's data is in but none of it is tagged for the current
   * week yet -- its trade-value sheet hasn't been re-pulled since the NFL
   * week turned over, so `rows` blends Draft Sharks alone rather than
   * silently mixing in Boone's stale prior-week numbers. */
  boonePending: boolean
  currentWeek: number | null
}

export function useBlendedRos(scoring: Scoring): BlendedRosResult {
  const { week: currentWeek, resolved: weekResolved } = useCurrentWeek()
  const [rows, setRows] = useState<BlendedRosRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)
  const [boonePending, setBoonePending] = useState(false)

  useEffect(() => {
    if (!weekResolved) return
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      // Paginated: Boone's "_latest" rows span every week (each player's own
      // latest), so they exceed PostgREST's 1000-row cap -- a plain select
      // truncated away the current week's rows and left Boone "pending".
      fetchAllRows<RosRankingRow>((from, to) =>
        supabase.from('in_season_ros_rankings_latest').select('*').eq('scoring', scoring).order('id').range(from, to),
      ),
      fetchAllRows<TradeValueLatestRow>((from, to) =>
        supabase.from('in_season_trade_values_latest').select('*').eq('source', 'boone').order('id').range(from, to),
      ),
    ]).then(([dsRes, booneRes]) => {
      if (cancelled) return
      if (dsRes.error) { setError(dsRes.error.message); setLoading(false); return }
      if (booneRes.error) { setError(booneRes.error.message); setLoading(false); return }

      // Both views serve each player their own latest row, which can be a
      // straggler left behind by an earlier pull (dropStaleStragglers) or,
      // for Boone specifically, an entire source that hasn't re-pulled for
      // the new NFL week yet (onlyWeek) -- either way, blending it in
      // unlabeled would misrepresent stale data as current.
      const dsRowsAll = dropStaleStragglers((dsRes.data ?? []) as RosRankingRow[])
      const booneRowsAll = dropStaleStragglers((booneRes.data ?? []) as TradeValueLatestRow[])
      const dsRows = onlyWeek(dsRowsAll, currentWeek, r => r.as_of_week)
      const booneRows = onlyWeek(booneRowsAll, currentWeek, r => r.week)
      const currentPulledAt = dsRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), dsRows[0]?.pulled_at ?? '')

      const blended = blendRosValues(
        dsRows.map(toDsRosInput),
        booneRows.map(r => toBooneRosInput(r, scoring)),
      )

      setRows(blended)
      setFreshest(currentPulledAt || null)
      setBoonePending(currentWeek != null && booneRowsAll.length > 0 && booneRows.length === 0)
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [scoring, currentWeek, weekResolved])

  return { rows, loading, error, freshest, boonePending, currentWeek }
}
