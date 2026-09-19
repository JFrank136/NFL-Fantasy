// src/lib/startSit.ts
//
// Pure calculations for the Start/Sit page: row-based comparison and the
// recommendation. No React, no Supabase.
//
// Anchor: the weighted weekly rank score (lower = better). It is on a shared
// scale for RB/WR/TE (FLEX) and separately for QBs, so a QB vs non-QB
// comparison gets no recommendation. See
// docs/superpowers/specs/2026-09-18-start-sit-and-add-drop-design.md.

import { highlightRow, round1, type CellFormat, type ComparisonRow, type Highlight } from './playerComparison'
import { FLEX_POSITIONS, formatOpponent, type WeeklyPlayer } from './weeklyPool'

/** Score-gap cutoffs (in weighted-rank points). Retune after a season of data. */
export const CONFIDENCE_THRESHOLDS = { high: 5, medium: 2 }
/** Smallest FLEX-rank gap worth calling out as a reason. */
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
