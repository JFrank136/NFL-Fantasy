// src/lib/tradeAnalyzer.ts
//
// Pure calculation functions for the Trade Analyzer page. No Supabase, no
// React -- the page fetches the same blended ROS rows Rankings uses (see
// useBlendedRos.ts) and hands the selected players here. Mirrors the
// roadmap's "Value Foundation" section: the blended ROS value (50% Draft
// Sharks / 50% Boone, already computed by blend.ts) is the trade metric,
// not average rank.

import type { BlendedRosRow } from './blend'

export interface TradeSideSummary {
  players: BlendedRosRow[]
  /** Sum of blendedValue across players that have one. Null only when the
   * side has players but none of them have a blended value yet (unmatched
   * to either source) -- an empty side reports 0, not null, so an empty
   * side can still be compared against a valued one. */
  totalValue: number | null
  bestPlayer: BlendedRosRow | null
}

export type TradeConfidence = 'Close' | 'Medium' | 'High'

export interface TradeComparison {
  sideA: TradeSideSummary
  sideB: TradeSideSummary
  /** sideA total minus sideB total. Positive favors side A. */
  diff: number | null
  /** abs(diff) as a fraction of the larger side's total (0-1). */
  pctDiff: number | null
  preferredSide: 'A' | 'B' | null
  confidence: TradeConfidence | null
  summary: string
}

/** Kept configurable per the roadmap ("Keep thresholds configurable") --
 * these will get tuned against real trade examples later rather than
 * treated as final. pctDiff is a 0-1 fraction of the larger side's total. */
export const CONFIDENCE_THRESHOLDS = {
  close: 0.08,
  medium: 0.20,
}

function summarizeSide(players: BlendedRosRow[]): TradeSideSummary {
  const valued = players.filter(p => p.blendedValue != null)
  const totalValue = valued.reduce((sum, p) => sum + (p.blendedValue as number), 0)

  let bestPlayer: BlendedRosRow | null = null
  for (const p of valued) {
    if (bestPlayer == null || (p.blendedValue as number) > (bestPlayer.blendedValue as number)) {
      bestPlayer = p
    }
  }

  return { players, totalValue: players.length ? totalValue : 0, bestPlayer }
}

function confidenceForPctDiff(pctDiff: number): TradeConfidence {
  if (pctDiff < CONFIDENCE_THRESHOLDS.close) return 'Close'
  if (pctDiff < CONFIDENCE_THRESHOLDS.medium) return 'Medium'
  return 'High'
}

/**
 * Compares two trade sides by total blended ROS value. Returns null
 * diff/pctDiff/preferredSide/confidence when either side has no players
 * yet, so the UI can show a neutral "add players" state instead of a
 * misleading 0% tie.
 */
export function evaluateTrade(sideAPlayers: BlendedRosRow[], sideBPlayers: BlendedRosRow[]): TradeComparison {
  const sideA = summarizeSide(sideAPlayers)
  const sideB = summarizeSide(sideBPlayers)

  if (sideAPlayers.length === 0 || sideBPlayers.length === 0) {
    return {
      sideA,
      sideB,
      diff: null,
      pctDiff: null,
      preferredSide: null,
      confidence: null,
      summary: 'Add at least one player to each side to evaluate this trade.',
    }
  }

  const totalA = sideA.totalValue as number
  const totalB = sideB.totalValue as number
  const diff = totalA - totalB
  const larger = Math.max(totalA, totalB)
  const pctDiff = larger > 0 ? Math.abs(diff) / larger : 0
  const confidence = confidenceForPctDiff(pctDiff)

  if (diff === 0) {
    return {
      sideA,
      sideB,
      diff,
      pctDiff,
      preferredSide: null,
      confidence,
      summary: 'Even trade -- both sides carry the same blended ROS value.',
    }
  }

  const preferredSide: 'A' | 'B' = diff > 0 ? 'A' : 'B'
  const winner = preferredSide === 'A' ? sideA : sideB
  const loser = preferredSide === 'A' ? sideB : sideA
  const winnerLabel = preferredSide === 'A' ? 'Side A' : 'Side B'
  const pct = Math.round(pctDiff * 100)

  let summary = `${winnerLabel} gets more value, up ${pct}% on blended ROS value (${confidence.toLowerCase()} confidence).`
  if (winner.bestPlayer && loser.bestPlayer && winner.bestPlayer.blendedValue != null && loser.bestPlayer.blendedValue != null) {
    if (winner.bestPlayer.blendedValue < loser.bestPlayer.blendedValue) {
      summary += ` ${loser.bestPlayer.playerName} is the best individual player in the deal, but ${winnerLabel.toLowerCase()} still comes out ahead on total value.`
    }
  }

  return { sideA, sideB, diff, pctDiff, preferredSide, confidence, summary }
}
