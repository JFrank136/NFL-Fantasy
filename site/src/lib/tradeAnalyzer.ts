// src/lib/tradeAnalyzer.ts
//
// Pure calculation functions for the Trade Analyzer page. No Supabase, no
// React -- the page fetches the same blended ROS rows Rankings uses (see
// useBlendedRos.ts) and hands the selected players here. Mirrors the
// roadmap's "Value Foundation" section: the blended ROS value (50% Draft
// Sharks / 50% Boone, already computed by blend.ts) is the trade metric,
// not average rank.

import { identityKey, type BlendedRosRow } from './blend'
import { valueForScoring, type Scoring, type TradeValueSourceRow } from './tradeValues'

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
  /** Side-by-side totals for each individual source (DS, Boone, then any
   * extra trade-value source with data for these players). Empty until both
   * sides have at least one player. */
  sources: SourceComparison[]
}

/** One source's view of the trade: each side's summed raw value in that
 * source's own scale (sources' scales differ, so only A-vs-B within a row is
 * meaningful, never across rows). */
export interface SourceComparison {
  source: string
  /** Null when no player on that side has a value in this source. */
  totalA: number | null
  totalB: number | null
  /** How many of each side's players have a value here -- less than the
   * side's size means that side's total is understated. */
  valuedA: number
  valuedB: number
  sizeA: number
  sizeB: number
  /** Null when the totals tie or either side has no value to compare. */
  winner: 'A' | 'B' | null
  /** abs(diff) as a fraction of the larger total (0-1); null if no winner comparison possible. */
  pctDiff: number | null
}

/** identityKey -> (source -> value) for sources beyond the two already on
 * BlendedRosRow (DS ROS value, Boone). */
export type ExtraSourceValues = Map<string, Record<string, number | null>>

/** Sources are discovered from the data; this only controls display order
 * (the two blend inputs first) and header text. */
export const PRIMARY_SOURCES = ['ds', 'boone'] as const
const SOURCE_LABELS: Record<string, string> = {
  ds: 'DS', boone: 'Boone', cbs: 'CBS', fantasypros: 'FantasyPros', rsj: 'RSJ', usatoday: 'USA Today',
}
export const tradeSourceLabel = (s: string) => SOURCE_LABELS[s] ?? s

/** Builds the extra-source lookup from long-format trade-value rows.
 * `exclude` drops sources already covered elsewhere (Boone lives on
 * BlendedRosRow; Draft Sharks' trade value IS its ROS ds_value). */
export function buildExtraSourceValues(
  rows: TradeValueSourceRow[],
  scoring: Scoring,
  exclude: string[] = ['boone', 'draftsharks'],
): ExtraSourceValues {
  const out: ExtraSourceValues = new Map()
  for (const row of rows) {
    if (exclude.includes(row.source)) continue
    const key = identityKey(row.canonicalName, row.position)
    const entry = out.get(key) ?? {}
    entry[row.source] = valueForScoring(row, scoring)
    out.set(key, entry)
  }
  return out
}

function playerSourceValues(player: BlendedRosRow, extras: ExtraSourceValues): Record<string, number | null> {
  return {
    ...extras.get(identityKey(player.canonicalName, player.position)),
    ds: player.dsValue,
    boone: player.booneValue,
  }
}

export function compareBySource(
  sideAPlayers: BlendedRosRow[],
  sideBPlayers: BlendedRosRow[],
  extras: ExtraSourceValues = new Map(),
): SourceComparison[] {
  const valuesA = sideAPlayers.map(p => playerSourceValues(p, extras))
  const valuesB = sideBPlayers.map(p => playerSourceValues(p, extras))

  const sources = new Set<string>()
  ;[...valuesA, ...valuesB].forEach(v => Object.entries(v).forEach(([s, val]) => { if (val != null) sources.add(s) }))

  const rank = (s: string) => {
    const i = (PRIMARY_SOURCES as readonly string[]).indexOf(s)
    return i === -1 ? PRIMARY_SOURCES.length : i
  }
  const ordered = Array.from(sources).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))

  const summarize = (values: Record<string, number | null>[], source: string) => {
    const valued = values.map(v => v[source]).filter((v): v is number => v != null)
    return { total: valued.length ? valued.reduce((sum, v) => sum + v, 0) : null, count: valued.length }
  }

  return ordered.map(source => {
    const a = summarize(valuesA, source)
    const b = summarize(valuesB, source)
    let winner: 'A' | 'B' | null = null
    let pctDiff: number | null = null
    if (a.total != null && b.total != null) {
      const larger = Math.max(a.total, b.total)
      pctDiff = larger > 0 ? Math.abs(a.total - b.total) / larger : 0
      if (a.total !== b.total) winner = a.total > b.total ? 'A' : 'B'
    }
    return {
      source, totalA: a.total, totalB: b.total, valuedA: a.count, valuedB: b.count,
      sizeA: sideAPlayers.length, sizeB: sideBPlayers.length, winner, pctDiff,
    }
  })
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
export function evaluateTrade(
  sideAPlayers: BlendedRosRow[],
  sideBPlayers: BlendedRosRow[],
  extras: ExtraSourceValues = new Map(),
): TradeComparison {
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
      sources: [],
    }
  }

  const totalA = sideA.totalValue as number
  const totalB = sideB.totalValue as number
  const diff = totalA - totalB
  const larger = Math.max(totalA, totalB)
  const pctDiff = larger > 0 ? Math.abs(diff) / larger : 0
  const confidence = confidenceForPctDiff(pctDiff)
  const sources = compareBySource(sideAPlayers, sideBPlayers, extras)

  if (diff === 0) {
    return {
      sideA,
      sideB,
      diff,
      pctDiff,
      preferredSide: null,
      confidence,
      summary: 'Even trade -- both sides carry the same blended ROS value.',
      sources,
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
      summary += ` ${loser.bestPlayer.playerName} is the best individual player in the deal, but ${winnerLabel} still comes out ahead on total value.`
    }
  }

  return { sideA, sideB, diff, pctDiff, preferredSide, confidence, summary, sources }
}
