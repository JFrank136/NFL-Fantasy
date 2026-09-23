// src/lib/useCurrentWeek.ts
//
// Shared "what NFL week is it" detection. Boone/Smyth only publish the
// current week (unlike Draft Sharks, which publishes all 18 weeks at once),
// so the max week they have data for IS the current week. Used both by the
// Weekly tab's own fetch and by anything that needs to gate "current" ROS/
// trade-value data against a source that hasn't refreshed for the new week
// yet (see freshness.ts).

import { useEffect, useState } from 'react'
import { supabase } from './supabase'

export interface CurrentWeekResult {
  week: number | null
  error: string | null
  // `week == null` is ambiguous on its own: still loading, or the query came
  // back empty? Without this flag consumers wait forever on an empty table.
  resolved: boolean
}

export function useCurrentWeek(): CurrentWeekResult {
  const [week, setWeek] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resolved, setResolved] = useState(false)

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
          setResolved(true)
          return
        }
        setWeek(data?.[0]?.week ?? null)
        setResolved(true)
      })
    return () => { cancelled = true }
  }, [])

  return { week, error, resolved }
}
