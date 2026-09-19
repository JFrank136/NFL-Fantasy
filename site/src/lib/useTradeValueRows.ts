// src/lib/useTradeValueRows.ts
//
// Every source's trade-value rows, for the Trade Analyzer's per-source
// comparison. Paginated (fetchAllRows) because all sources together exceed
// PostgREST's 1000-row cap. Failure is reported but non-fatal to callers --
// the analyzer still works off DS + Boone without these.

import { useEffect, useState } from 'react'
import { supabase, fetchAllRows, type TradeValueLatestRow } from './supabase'
import type { TradeValueSourceRow } from './tradeValues'

export function toTradeValueSourceRow(r: TradeValueLatestRow): TradeValueSourceRow {
  return {
    source: r.source,
    playerName: r.player_name,
    canonicalName: r.canonical_name,
    team: r.team,
    position: r.position,
    valueCol1Label: r.value_col1_label,
    valueCol1: r.value_col1,
    valueCol2Label: r.value_col2_label,
    valueCol2: r.value_col2,
  }
}

export function useTradeValueRows(): { rows: TradeValueSourceRow[]; error: string | null } {
  const [rows, setRows] = useState<TradeValueSourceRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchAllRows<TradeValueLatestRow>((from, to) =>
      supabase.from('in_season_trade_values_latest').select('*').order('id').range(from, to),
    ).then(res => {
      if (cancelled) return
      if (res.error) setError(res.error.message)
      else setRows(res.data.map(toTradeValueSourceRow))
    })
    return () => { cancelled = true }
  }, [])

  return { rows, error }
}
