// src/lib/startSit.ts
//
// Pure calculations for the Start/Sit page: row-based comparison and the
// recommendation. No React, no Supabase.
//
// Anchor: the weighted weekly rank score (lower = better). All three sources
// are put on one scale first: Boone and Smyth rank within Yahoo's FLX
// (RB/WR/TE) and QB groups already, and Draft Sharks' overall weekly rank is
// rescaled into those same two groups by blend.ts's rescaleDraftSharksRanks
// before the weighted average. The score is therefore comparable within
// RB/WR/TE and, separately, within QB -- but NOT between the two, so a QB vs
// non-QB comparison gets no recommendation and no highlights. See
// docs/superpowers/specs/2026-09-18-start-sit-and-add-drop-design.md.

import { highlightRow, round1, type CellFormat, type ComparisonRow, type Highlight } from './playerComparison'
import { FLEX_POSITIONS, formatOpponent, type WeeklyPlayer } from './weeklyPool'

/**
 * Score-gap cutoffs, in weighted-rank points.
 *
 * Measured on live week-2 2026 PPR data (369 playable RB/WR/TE, 36 QB) after
 * rescaleDraftSharksRanks, which is what made score points mean something:
 * a score point is now almost exactly one place, at every depth.
 *  - FLEX adjacent-pair gap: mean 1.17 / 0.85 / 0.96 / 0.97 / 1.00 for ranks
 *    1-10, 10-30, 30-60, 60-100 and 100+; max 3.43 anywhere.
 *  - FLEX median gap for a fixed rank distance: ~1 at 1 place, ~3 at 3,
 *    ~5 at 5, ~9.5 at 10 -- flat across all five depth buckets.
 *  - QB behaves the same (adjacent mean 0.73-0.96, ~9.4 at 10 places), so one
 *    set of numbers covers both groups.
 * Before the rescale the same measurement was wildly depth-dependent (FLEX
 * rank 100+ adjacent gaps averaged 2.79 with a max of 20 vs 2.22/3.60 at
 * ranks 1-10; QB ranks 30-60 averaged 51.2 with a max of 282.6), which is
 * why deep comparisons used to report "High" on noise.
 *
 * So the cutoffs are chosen as rank distances:
 *  - high 8: roughly 8-10 places apart. 91% of 10-apart FLEX pairs clear it,
 *    only 2% of 5-apart pairs do.
 *  - medium 3: roughly 3-5 places apart. 64% of 3-apart and 94% of 5-apart
 *    FLEX pairs clear it, 1% of adjacent pairs do.
 *  - below that: within ~2 places, which is ordinary disagreement between
 *    three analysts, so "Toss-up".
 */
export const CONFIDENCE_THRESHOLDS = { high: 8, medium: 3 }
/**
 * Smallest FLEX-rank gap worth calling out as a reason. Re-checked against
 * the same week-2 sample: 5 places is a median score gap of ~5 points, i.e.
 * comfortably inside "Medium" and most of the way to "High", while adjacent
 * and 3-apart pairs (ordinary noise) never reach it. Kept at 5.
 */
export const FLEX_GAP_NOTE_MIN = 5
/** Smallest ceiling / projection edge worth calling out as a reason (points). */
export const CEILING_NOTE_MIN = 2
export const PROJECTION_NOTE_MIN = 1

export type Confidence = 'High' | 'Medium' | 'Toss-up'

export interface StartSitRecommendation {
  status: 'ok' | 'not-comparable' | 'insufficient'
  starterKey: string | null
  confidence: Confidence | null
  reasons: string[]
  note: string | null
}

/** RB/WR/TE share one scale ("FLEX"); every other position is its own group. */
const scaleGroup = (p: WeeklyPlayer) => (FLEX_POSITIONS.includes(p.position) ? 'FLEX' : p.position)

/**
 * What has to be true of the selection before a row's values can be compared:
 * - 'scale': only within one scale group (FLEX or QB). Ranks and projections
 *   are on their own scale per group, so a QB's #2 or 22-point projection is
 *   not "better" than an RB's #40 or 11 points -- it is a different yardstick.
 *   Within FLEX, RB/WR/TE projections ARE comparable, which is the whole point
 *   of a FLEX decision, so these stay highlighted for RB vs WR.
 * - 'position': only when every player shares a position (position rank).
 * - 'always': safe regardless (FLEX rank is null for QBs anyway).
 */
type HighlightGate = 'always' | 'scale' | 'position'

interface RowSpec {
  id: string
  label: string
  format: CellFormat
  /** null = show but never highlight. */
  better: 'higher' | 'lower' | null
  gate: HighlightGate
  pick: (p: WeeklyPlayer, rosByKey: Map<string, number | null>) => number | string | null
}

const ROW_SPECS: RowSpec[] = [
  { id: 'score', label: 'Rank score (lower = better)', format: 'value', better: 'lower', gate: 'scale', pick: p => p.aggregateScore },
  { id: 'positionRank', label: 'Position rank', format: 'rank', better: 'lower', gate: 'position', pick: p => p.positionRank },
  { id: 'flexRank', label: 'FLEX rank (RB/WR/TE)', format: 'rank', better: 'lower', gate: 'always', pick: p => p.flexRank },
  { id: 'dsRank', label: 'Draft Sharks rank (FLEX/QB scale)', format: 'rank', better: 'lower', gate: 'scale', pick: p => p.dsRank },
  { id: 'booneRank', label: 'Boone rank', format: 'rank', better: 'lower', gate: 'scale', pick: p => p.booneRank },
  { id: 'smytheRank', label: 'Smyth rank', format: 'rank', better: 'lower', gate: 'scale', pick: p => p.smytheRank },
  { id: 'dsProjection', label: 'DS projection', format: 'value', better: 'higher', gate: 'scale', pick: p => p.dsProjection },
  { id: 'dsFloor', label: 'DS floor', format: 'value', better: 'higher', gate: 'scale', pick: p => p.dsFloor },
  { id: 'dsCeiling', label: 'DS ceiling', format: 'value', better: 'higher', gate: 'scale', pick: p => p.dsCeiling },
  // Display only: no matchup-rating source exists yet.
  { id: 'opponent', label: 'Opponent', format: 'text', better: null, gate: 'always', pick: p => formatOpponent(p.opponent) },
  // Context only, never used in the recommendation.
  { id: 'ros', label: 'ROS value (context)', format: 'value', better: null, gate: 'always', pick: (p, ros) => ros.get(p.key) ?? null },
]

/** Row-based comparison (one row per stat, one column per player). */
export function startSitRows(players: WeeklyPlayer[], rosByKey: Map<string, number | null>): ComparisonRow[] {
  // Bye-week players don't count: they're excluded from highlights anyway.
  const playing = players.filter(p => !p.isBye)
  const samePosition = new Set(playing.map(p => p.position)).size <= 1
  // Same boundary recommendStartSit refuses to cross, so the table can't
  // quietly crown a "best" QB in a comparison the recommendation declines.
  const sameScale = new Set(playing.map(scaleGroup)).size <= 1
  return ROW_SPECS.map(spec => {
    const values = players.map(p => spec.pick(p, rosByKey))
    const gateOpen = spec.gate === 'always' || (spec.gate === 'scale' ? sameScale : samePosition)
    const canHighlight = spec.better != null && spec.format !== 'text' && gateOpen
    let highlights: Highlight[] = values.map(() => null)
    if (canHighlight) {
      // A bye-week player's numbers shouldn't decide who is best/worst.
      const forHighlight = values.map((v, i) => (players[i].isBye ? null : v)) as (number | null)[]
      highlights = highlightRow(forHighlight, spec.better as 'higher' | 'lower')
    }
    return { id: spec.id, label: spec.label, format: spec.format, values, highlights }
  })
}

function confidenceFor(gap: number): Confidence {
  if (gap >= CONFIDENCE_THRESHOLDS.high) return 'High'
  if (gap >= CONFIDENCE_THRESHOLDS.medium) return 'Medium'
  return 'Toss-up'
}

function buildReasons(top: WeeklyPlayer, next: WeeklyPlayer): string[] {
  const reasons: string[] = []

  if (top.dsRank != null && next.dsRank != null && top.booneRank != null && next.booneRank != null) {
    const dsSign = Math.sign(next.dsRank - top.dsRank) // > 0: Draft Sharks favors the starter
    const booneSign = Math.sign(next.booneRank - top.booneRank)
    const favored = (s: number) => (s > 0 ? top : next)
    if (dsSign > 0 && booneSign > 0) {
      reasons.push(`Ranked ahead of ${next.playerName} by both Draft Sharks and Boone.`)
    } else if (dsSign < 0 && booneSign < 0) {
      reasons.push(`Draft Sharks and Boone both rank ${next.playerName} ahead; the weighted score favors ${top.playerName} (Smyth/weights).`)
    } else if (dsSign * booneSign < 0) {
      reasons.push(`Sources split: Draft Sharks favors ${favored(dsSign).playerName}, Boone favors ${favored(booneSign).playerName}.`)
    }
  }

  if (top.flexRank != null && next.flexRank != null && next.flexRank - top.flexRank >= FLEX_GAP_NOTE_MIN) {
    reasons.push(`FLEX rank #${top.flexRank} vs #${next.flexRank} for ${next.playerName}.`)
  }

  if (top.dsCeiling != null && next.dsCeiling != null && next.dsCeiling - top.dsCeiling >= CEILING_NOTE_MIN) {
    reasons.push(`${next.playerName} has the higher ceiling (${round1(next.dsCeiling)} vs ${round1(top.dsCeiling)}).`)
  } else if (top.dsProjection != null && next.dsProjection != null && top.dsProjection - next.dsProjection >= PROJECTION_NOTE_MIN) {
    reasons.push(`Projected ${round1(top.dsProjection)} pts vs ${round1(next.dsProjection)}.`)
  }

  if (reasons.length === 0) {
    reasons.push(`Rank score ${round1(top.aggregateScore as number)} vs ${round1(next.aggregateScore as number)}.`)
  }
  return reasons.slice(0, 2)
}

export function recommendStartSit(players: WeeklyPlayer[]): StartSitRecommendation {
  const byes = players.filter(p => p.isBye)
  const byeNote = byes.length
    ? `${byes.map(p => p.playerName).join(', ')} ${byes.length === 1 ? 'is' : 'are'} on a bye and excluded.`
    : null
  const valid = players.filter(p => !p.isBye && p.aggregateScore != null)

  if (valid.length < 2) {
    return {
      status: 'insufficient', starterKey: null, confidence: null, reasons: [],
      note: [byeNote, 'Add at least two players who are playing this week and have a ranking.'].filter(Boolean).join(' '),
    }
  }

  if (new Set(valid.map(scaleGroup)).size > 1) {
    return {
      status: 'not-comparable', starterKey: null, confidence: null, reasons: [],
      note: [
        byeNote,
        "QBs are ranked against QBs only, so a QB can't be compared with an RB, WR or TE. Compare like with like.",
      ].filter(Boolean).join(' '),
    }
  }

  const sorted = [...valid].sort((a, b) => (a.aggregateScore as number) - (b.aggregateScore as number))
  const top = sorted[0]
  const next = sorted[1]
  // Round away floating-point noise (e.g. 3.3 - 1.3 = 1.9999999999999998) before thresholding.
  const gap = Math.round(((next.aggregateScore as number) - (top.aggregateScore as number)) * 1000) / 1000

  return {
    status: 'ok',
    starterKey: top.key,
    confidence: confidenceFor(gap),
    reasons: buildReasons(top, next),
    note: byeNote,
  }
}
