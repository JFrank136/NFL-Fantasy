// src/lib/useWeeklyRows.ts
//
// Shared "current week's aggregated weekly rankings" fetch. Extracted from
// Rankings' weekly tab so Start/Sit and Add/Drop reuse the exact same fetch,
// grouping and aggregation instead of re-deriving it per page.

import { useEffect, useState } from 'react'
import { supabase, fetchAllRows, type RankingLatestRow } from './supabase'
import { aggregateWeeklyRanks, identityKey, normalizePosition, type AggregatedWeeklyRow } from './blend'
import type { Scoring } from './useBlendedRos'

export function useCurrentWeek() {
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

export interface WeeklyRowsResult {
  rows: AggregatedWeeklyRow[]
  week: number | null
  loading: boolean
  error: string | null
  freshest: string | null
}

export function useWeeklyRows(scoring: Scoring): WeeklyRowsResult {
  const { week, error: weekError } = useCurrentWeek()
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

    // One week across all sources is ~1400 rows (DS alone includes DL/K/DST),
    // over PostgREST's 1000-row cap -- paginate or later players (e.g. a QB's
    // DS row) silently drop out.
    fetchAllRows<RankingLatestRow>((from, to) =>
      supabase
        .from('in_season_rankings_latest')
        .select('*')
        .eq('scoring', scoring)
        .eq('week', week)
        .order('id')
        .range(from, to),
    )
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) { setError(error.message); setLoading(false); return }

        const rankingRows = data
        const byPlayer = new Map<string, RankingLatestRow[]>()
        rankingRows.forEach(r => {
          const key = identityKey(r.canonical_name, r.position)
          const list = byPlayer.get(key) ?? []
          list.push(r)
          byPlayer.set(key, list)
        })

        const players = Array.from(byPlayer.values()).map(sourceRows => {
          const ds = sourceRows.find(r => r.source === 'draftsharks')
          const boone = sourceRows.find(r => r.source === 'boone')
          const smythe = sourceRows.find(r => r.source === 'smythe')
          const any = ds ?? boone ?? smythe ?? sourceRows[0]
          return {
            canonicalName: any.canonical_name,
            playerName: any.player_name,
            position: normalizePosition(any.position),
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

  return { rows, week, loading, error, freshest }
}
