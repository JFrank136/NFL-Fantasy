// src/lib/supabase.ts
//
// Thin Supabase client for the site. Talks to the same "Fantasy Football"
// project (tdtchffawcmkvgrccjza) Vampire/BigBallerLeague already use, via
// the public anon/publishable key (safe to ship to the browser -- RLS is
// off on these tables, a deliberate low-stakes/no-login tradeoff already
// made for the sibling vampire_* tables). See in-season/docs/DATA.md for
// the full schema this client reads.

import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY -- copy .env.example to .env and fill them in.'
  )
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// Row shapes for the two "latest" views (in_season_rankings_latest /
// in_season_trade_values_latest) -- these are what pages should query
// against, not the raw append-only tables, unless a page specifically
// needs historical rows (e.g. Movers & Fallers).
export interface RankingLatestRow {
  id: number
  season: number
  week: number
  source: string
  scoring: string
  pulled_at: string
  source_player_id: string
  player_name: string
  canonical_name: string
  team: string | null
  position: string
  rank: number | null
  projection: number | null
  floor_proj: number | null
  ceiling_proj: number | null
  tier: number | null
  bye: number | null
  opponent: string | null
}

export interface TradeValueLatestRow {
  id: number
  season: number
  week: number
  source: string
  position: string
  pulled_at: string
  source_url: string
  rank: number | null
  player_name: string
  canonical_name: string
  team: string | null
  value_col1_label: string
  value_col1: number | null
  value_col2_label: string
  value_col2: number | null
}

// Row shape for in_season_ros_rankings_latest.
export interface RosRankingRow {
  id: number
  season: number
  source: string
  scoring: string
  pulled_at: string
  as_of_week: number
  source_player_id: string
  player_name: string
  canonical_name: string
  team: string | null
  position: string
  rank: number | null
  tier_overall: number | null
  tier_positional: number | null
  projection: number | null
  floor_proj: number | null
  ceiling_proj: number | null
  ds_value: number | null
  strength_of_schedule: string | null
  games_played: number | null
  injury_risk: string | null
  bye: number | null
}

export interface PullStatusRow {
  dataset: string
  last_success_at: string | null
  last_attempt_at: string
  status: 'healthy' | 'warning' | 'failed'
  message: string | null
  row_count: number | null
}
