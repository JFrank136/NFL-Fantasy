// src/lib/useRosHistory.ts
//
// Fetches the full append-only history behind the blended ROS value: every
// Draft Sharks ROS pull for a scoring format and every Boone trade-value
// pull. Movers & Fallers picks current/baseline snapshots out of this
// client-side (see movers.ts splitSnapshots). Paginated via fetchAllRows because
// the full history exceeds Supabase's silent 1000-row response cap.

import { useEffect, useState } from 'react'
import { supabase, fetchAllRows, type RosRankingRow, type TradeValueLatestRow } from './supabase'
import type { Scoring } from './useBlendedRos'

export interface RosHistoryResult {
  dsRows: RosRankingRow[]
  booneRows: TradeValueLatestRow[]
  loading: boolean
  error: string | null
}

export function useRosHistory(scoring: Scoring): RosHistoryResult {
  const [dsRows, setDsRows] = useState<RosRankingRow[]>([])
  const [booneRows, setBooneRows] = useState<TradeValueLatestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      fetchAllRows<RosRankingRow>((from, to) =>
        supabase.from('in_season_ros_rankings').select('*').eq('scoring', scoring)
          .order('id').range(from, to)),
      fetchAllRows<TradeValueLatestRow>((from, to) =>
        supabase.from('in_season_trade_values').select('*').eq('source', 'boone')
          .order('id').range(from, to)),
    ]).then(([ds, boone]) => {
      if (cancelled) return
      const failure = ds.error ?? boone.error
      if (failure) setError(failure.message)
      else {
        setDsRows(ds.data)
        setBooneRows(boone.data)
      }
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [scoring])

  return { dsRows, booneRows, loading, error }
}
