// src/lib/rosHistory.ts
//
// Fetches the ROS/trade-value snapshot immediately before the current one,
// for the ROS tab's "ROS change" column. Kept separate from blend.ts so
// that file stays pure/synchronous and independently testable.

import { supabase, type RosRankingRow, type TradeValueLatestRow } from './supabase'

/**
 * Returns Draft Sharks ROS rows and Boone trade-value rows from the most
 * recent pull *before* `currentPulledAt`, or null if no earlier pull
 * exists yet (e.g. the very first week of this pipeline running).
 */
export async function fetchPreviousRosSnapshot(
  scoring: 'half-ppr' | 'ppr',
  currentPulledAt: string,
): Promise<{ dsRows: RosRankingRow[]; booneRows: TradeValueLatestRow[] } | null> {
  const { data: priorPulls, error: priorPullsError } = await supabase
    .from('in_season_ros_rankings')
    .select('pulled_at')
    .eq('scoring', scoring)
    .lt('pulled_at', currentPulledAt)
    .order('pulled_at', { ascending: false })
    .limit(1)
  if (priorPullsError) console.error('Failed to fetch prior pulls:', priorPullsError)

  const previousPulledAt = priorPulls?.[0]?.pulled_at
  if (!previousPulledAt) return null

  const { data: dsRows, error: dsRowsError } = await supabase
    .from('in_season_ros_rankings')
    .select('*')
    .eq('scoring', scoring)
    .eq('pulled_at', previousPulledAt)
  if (dsRowsError) console.error('Failed to fetch prior DS ROS rows:', dsRowsError)

  const { data: priorTradeValuePulls, error: priorTradeValuePullsError } = await supabase
    .from('in_season_trade_values')
    .select('pulled_at')
    .eq('source', 'boone')
    .lt('pulled_at', currentPulledAt)
    .order('pulled_at', { ascending: false })
    .limit(1)
  if (priorTradeValuePullsError) console.error('Failed to fetch prior trade value pulls:', priorTradeValuePullsError)

  const previousTradeValuePulledAt = priorTradeValuePulls?.[0]?.pulled_at
  let booneRows: TradeValueLatestRow[] = []
  if (previousTradeValuePulledAt) {
    const { data, error: booneRowsError } = await supabase
      .from('in_season_trade_values')
      .select('*')
      .eq('source', 'boone')
      .eq('pulled_at', previousTradeValuePulledAt)
    if (booneRowsError) console.error('Failed to fetch prior Boone trade value rows:', booneRowsError)
    booneRows = (data ?? []) as TradeValueLatestRow[]
  }

  return { dsRows: (dsRows ?? []) as RosRankingRow[], booneRows }
}
