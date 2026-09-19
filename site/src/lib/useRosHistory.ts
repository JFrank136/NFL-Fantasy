// src/lib/useRosHistory.ts
//
// Fetches the full append-only history behind the blended ROS value: every
// Draft Sharks ROS pull for a scoring format and every Boone trade-value
// pull. Movers & Fallers picks current/baseline snapshots out of this
// client-side (see movers.ts splitSnapshots). History is small (hundreds of
// rows per pull), so pages of 1000 are fetched until exhausted rather than
// relying on the API's default row cap.

import { useEffect, useState } from 'react'
import { supabase, type RosRankingRow, type TradeValueLatestRow } from './supabase'
import type { Scoring } from './useBlendedRos'

const PAGE_SIZE = 1000

async function fetchAll<T>(
  page: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
): Promise<T[]> {
  const all: T[] = []
  for (let from = 0; ; from += PAGE_SIZE) {
    const { data, error } = await page(from, from + PAGE_SIZE - 1)
    if (error) throw new Error(error.message)
    const rows = data ?? []
    all.push(...rows)
    if (rows.length < PAGE_SIZE) return all
  }
}

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
      fetchAll<RosRankingRow>((from, to) =>
        supabase.from('in_season_ros_rankings').select('*').eq('scoring', scoring)
          .order('id').range(from, to)),
      fetchAll<TradeValueLatestRow>((from, to) =>
        supabase.from('in_season_trade_values').select('*').eq('source', 'boone')
          .order('id').range(from, to)),
    ])
      .then(([ds, boone]) => {
        if (cancelled) return
        setDsRows(ds)
        setBooneRows(boone)
        setLoading(false)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(e.message)
        setLoading(false)
      })

    return () => { cancelled = true }
  }, [scoring])

  return { dsRows, booneRows, loading, error }
}
