// src/lib/weeklyPool.ts
//
// Shared weekly player shape for Start/Sit and Add/Drop. Pure: no React, no
// Supabase. Built from Rankings' AggregatedWeeklyRow output.
//
// FLEX rank: aggregateWeeklyRanks re-ranks within each position, so "RB4 vs
// RB6" hides how far apart they are overall. Before that re-rank, the
// weighted score is on a shared scale for RB/WR/TE: Boone and Smyth are
// pulled from Yahoo's FLX query, and Draft Sharks' weekly rank -- which is an
// OVERALL rank across everything it publishes, IDP/K/DST included -- is
// rescaled into the same RB/WR/TE (FLEX) and QB groups by blend.ts's
// rescaleDraftSharksRanks before the blend. So ranking every RB/WR/TE by that
// score gives a real cross-position rank. QBs are scaled and ranked against
// QBs only, so they get no FLEX rank, and a QB score is never comparable with
// an RB/WR/TE score.

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
  /**
   * Draft Sharks' rank rescaled into the FLEX/QB group, so it is directly
   * comparable with booneRank/smytheRank (Start/Sit's source-agreement and
   * source-split reasons compare the three against each other).
   */
  dsRank: number | null
  /** Draft Sharks' published overall rank, unscaled. Display/debug only. */
  dsOverallRank: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
}

/**
 * True when a row is on a bye for `week`. Two signals, because sources don't
 * agree: an empty `opponent` (Draft Sharks drops it), or the stored `bye`
 * column matching the week being shown (Yahoo keeps an opponent string).
 */
export function isByeWeek(row: Pick<AggregatedWeeklyRow, 'opponent' | 'byeWeek'>, week: number | null): boolean {
  return !row.opponent || (week != null && row.byeWeek === week)
}

/**
 * FLEX rank by identity key. Only scored, non-bye RB/WR/TE rows are ranked;
 * ties share a rank (competition ranking: 1, 1, 3).
 */
export function computeFlexRanks(rows: AggregatedWeeklyRow[], week: number | null): Map<string, number> {
  const eligible = rows.filter(
    r => FLEX_POSITIONS.includes(r.position) && r.aggregateScore != null && !isByeWeek(r, week),
  )
  const scores = eligible.map(r => r.aggregateScore as number)
  const ranks = new Map<string, number>()
  eligible.forEach(r => {
    const better = scores.filter(s => s < (r.aggregateScore as number)).length
    ranks.set(identityKey(r.canonicalName, r.position), better + 1)
  })
  return ranks
}

export function buildWeeklyPool(rows: AggregatedWeeklyRow[], week: number | null): WeeklyPlayer[] {
  const flex = computeFlexRanks(rows, week)
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
        isBye: isByeWeek(r, week),
        aggregateScore: r.aggregateScore,
        positionRank: r.aggregateRank,
        flexRank: flex.get(key) ?? null,
        dsRank: r.draftsharksScaledRank ?? r.draftsharksRank,
        dsOverallRank: r.draftsharksRank,
        booneRank: r.booneRank,
        smytheRank: r.smytheRank,
        dsProjection: r.dsProjection,
        dsFloor: r.dsFloor,
        dsCeiling: r.dsCeiling,
      }
    })
}

/**
 * "@KC" stays, "at IND" -> "@IND", "NO" -> "vs NO", empty -> "BYE".
 * Yahoo (Boone/Smyth) already writes home games as "vs. DET", so a leading
 * "vs"/"vs." is stripped first -- otherwise the fallback renders "vs vs. DET".
 */
export function formatOpponent(opponent: string | null): string {
  if (!opponent) return 'BYE'
  if (opponent.startsWith('@')) return opponent
  const at = opponent.match(/^at\s+(.+)$/i)
  if (at) return `@${at[1]}`
  return `vs ${opponent.replace(/^vs\.?\s+/i, '')}`
}
