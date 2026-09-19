// src/lib/weeklyPool.ts
//
// Shared weekly player shape for Start/Sit and Add/Drop. Pure: no React, no
// Supabase. Built from Rankings' AggregatedWeeklyRow output.
//
// FLEX rank: aggregateWeeklyRanks re-ranks within each position, so "RB4 vs
// RB6" hides how far apart they are overall. Before that re-rank, the
// weighted score is on a shared scale for RB/WR/TE (Boone/Smyth are pulled
// from Yahoo's FLX query; Draft Sharks ranks overall), so ranking every
// RB/WR/TE by that score gives a cross-position rank. QBs are ranked against
// QBs only, so they get none.

import { identityKey, type AggregatedWeeklyRow } from './blend'

export const WEEKLY_POSITIONS = ['QB', 'RB', 'WR', 'TE']
export const FLEX_POSITIONS = ['RB', 'WR', 'TE']

export interface WeeklyPlayer {
  key: string
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  /** Raw opponent string as stored, e.g. "@KC". Null/empty = bye week. */
  opponent: string | null
  isBye: boolean
  /** Weighted average of source ranks (lower = better). The recommendation anchor. */
  aggregateScore: number | null
  positionRank: number | null
  flexRank: number | null
  dsRank: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
}

/**
 * FLEX rank by identity key. Only scored, non-bye RB/WR/TE rows are ranked;
 * ties share a rank (competition ranking: 1, 1, 3).
 */
export function computeFlexRanks(rows: AggregatedWeeklyRow[]): Map<string, number> {
  const eligible = rows.filter(
    r => FLEX_POSITIONS.includes(r.position) && r.aggregateScore != null && !!r.opponent,
  )
  const scores = eligible.map(r => r.aggregateScore as number)
  const ranks = new Map<string, number>()
  eligible.forEach(r => {
    const better = scores.filter(s => s < (r.aggregateScore as number)).length
    ranks.set(identityKey(r.canonicalName, r.position), better + 1)
  })
  return ranks
}

export function buildWeeklyPool(rows: AggregatedWeeklyRow[]): WeeklyPlayer[] {
  const flex = computeFlexRanks(rows)
  return rows
    .filter(r => WEEKLY_POSITIONS.includes(r.position))
    .map(r => {
      const key = identityKey(r.canonicalName, r.position)
      return {
        key,
        canonicalName: r.canonicalName,
        playerName: r.playerName,
        position: r.position,
        team: r.team,
        opponent: r.opponent,
        isBye: !r.opponent,
        aggregateScore: r.aggregateScore,
        positionRank: r.aggregateRank,
        flexRank: flex.get(key) ?? null,
        dsRank: r.draftsharksRank,
        booneRank: r.booneRank,
        smytheRank: r.smytheRank,
        dsProjection: r.dsProjection,
        dsFloor: r.dsFloor,
        dsCeiling: r.dsCeiling,
      }
    })
}

/** "@KC" stays, "at IND" -> "@IND", "NO" -> "vs NO", empty -> "BYE". */
export function formatOpponent(opponent: string | null): string {
  if (!opponent) return 'BYE'
  if (opponent.startsWith('@')) return opponent
  const at = opponent.match(/^at\s+(.+)$/i)
  if (at) return `@${at[1]}`
  return `vs ${opponent}`
}
