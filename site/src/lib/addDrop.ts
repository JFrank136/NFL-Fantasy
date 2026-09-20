// src/lib/addDrop.ts
//
// Pure calculations for the Add/Drop page. No React, no Supabase.
//
// Two-step problem: (1) is anyone worth adding? (2) if so, who to drop?
// ROS value ("who is better right now") and DS ceiling ("who has the better
// best case") stay separate axes -- no combined score in v1, and no
// cross-position logic.

import { highlightRow, round1, type CellFormat, type ComparisonPlayer, type ComparisonRow } from './playerComparison'
import type { WeeklyPlayer } from './weeklyPool'

/**
 * Blended-ROS-value gap (best add minus weakest drop) cutoffs. Tunable.
 * Values are trade-value-style; sampling live data showed 1.5 was only ~5-7
 * waiver-zone ranks (noise), so Marginal starts at 2.
 */
export const ADD_DROP_THRESHOLDS = { yes: 5, marginal: 2 }
/**
 * Smallest DS-ceiling edge worth calling out. Two random bench players differ
 * by >=2 ceiling ~53% of the time and >=3 ~40%, so 3 keeps the note meaningful.
 */
export const UPSIDE_NOTE_MIN = 3

export type Verdict = 'Yes' | 'Marginal' | 'No'

export interface AddDropAnalysis {
  status: 'ok' | 'insufficient'
  verdict: Verdict | null
  bestAdd: ComparisonPlayer | null
  /** Lowest-ROS-value drop candidate: who to drop if you do add. */
  dropTarget: ComparisonPlayer | null
  /** Best add's blended value minus drop target's. */
  gap: number | null
  upsideNote: string | null
  dropCaveat: string | null
}

const INSUFFICIENT: AddDropAnalysis = {
  status: 'insufficient', verdict: null, bestAdd: null, dropTarget: null, gap: null, upsideNote: null, dropCaveat: null,
}

/** Difference of two decimals rounded to 3 places so float error (2.8 - 1.3 = 1.4999999999999998) can't misfire a threshold. */
function diff(a: number, b: number): number {
  return Math.round((a - b) * 1000) / 1000
}

function verdictFor(gap: number): Verdict {
  if (gap >= ADD_DROP_THRESHOLDS.yes) return 'Yes'
  if (gap >= ADD_DROP_THRESHOLDS.marginal) return 'Marginal'
  return 'No'
}

export function analyzeAddDrop(adds: ComparisonPlayer[], drops: ComparisonPlayer[]): AddDropAnalysis {
  const valuedAdds = adds.filter(p => p.blended != null)
  const valuedDrops = drops.filter(p => p.blended != null)
  if (valuedAdds.length === 0 || valuedDrops.length === 0) return INSUFFICIENT

  const bestAdd = valuedAdds.reduce((a, b) => ((b.blended as number) > (a.blended as number) ? b : a))
  const dropTarget = valuedDrops.reduce((a, b) => ((b.blended as number) < (a.blended as number) ? b : a))
  const gap = diff(bestAdd.blended as number, dropTarget.blended as number)

  // Upside: the add with the highest ceiling vs the drop target.
  let upsideNote: string | null = null
  const withCeiling = adds.filter(p => p.ceiling != null)
  if (withCeiling.length > 0 && dropTarget.ceiling != null) {
    const upsideAdd = withCeiling.reduce((a, b) => ((b.ceiling as number) > (a.ceiling as number) ? b : a))
    if (diff(upsideAdd.ceiling as number, dropTarget.ceiling) >= UPSIDE_NOTE_MIN) {
      upsideNote = `${upsideAdd.playerName} has the higher ceiling than ${dropTarget.playerName} (${round1(upsideAdd.ceiling as number)} vs ${round1(dropTarget.ceiling)}).`
    }
  }

  // Caveat: the suggested drop is lowest on ROS but has more upside than the add.
  let dropCaveat: string | null = null
  if (bestAdd.ceiling != null && dropTarget.ceiling != null && diff(dropTarget.ceiling, bestAdd.ceiling) >= UPSIDE_NOTE_MIN) {
    dropCaveat = `${dropTarget.playerName} is the lowest ROS value but has a higher ceiling than ${bestAdd.playerName} (${round1(dropTarget.ceiling)} vs ${round1(bestAdd.ceiling)}). Consider dropping someone else.`
  }

  return { status: 'ok', verdict: verdictFor(gap), bestAdd, dropTarget, gap, upsideNote, dropCaveat }
}

interface RowSpec {
  id: string
  label: string
  format: CellFormat
  better: 'higher' | 'lower' | null
  pick: (p: ComparisonPlayer, weekly: WeeklyPlayer | undefined) => number | string | null
}

const ROW_SPECS: RowSpec[] = [
  { id: 'blended', label: 'Blended ROS value', format: 'value', better: 'higher', pick: p => p.blended },
  { id: 'ceiling', label: 'DS ceiling (upside)', format: 'value', better: 'higher', pick: p => p.ceiling },
  { id: 'trend', label: 'ROS trend', format: 'signed', better: 'higher', pick: p => p.trend },
  // Direction of Draft Sharks' SOS percentage isn't documented: context only.
  { id: 'sos', label: 'Strength of schedule', format: 'text', better: null, pick: p => p.sos },
  { id: 'weekProjection', label: 'This week: DS projection', format: 'value', better: 'higher', pick: (_p, w) => (w && !w.isBye ? w.dsProjection : null) },
  { id: 'weekPositionRank', label: 'This week: position rank', format: 'rank', better: 'lower', pick: (_p, w) => (w && !w.isBye ? w.positionRank : null) },
  { id: 'weekFlexRank', label: 'This week: FLEX rank', format: 'rank', better: 'lower', pick: (_p, w) => (w && !w.isBye ? w.flexRank : null) },
]

/**
 * Row-based comparison across every selected player (adds and drops
 * together, so the best/worst highlight spans both lists).
 */
export function addDropRows(players: ComparisonPlayer[], weeklyByKey: Map<string, WeeklyPlayer>): ComparisonRow[] {
  const samePosition = new Set(players.map(p => p.position)).size <= 1
  return ROW_SPECS.map(spec => {
    const values = players.map(p => spec.pick(p, weeklyByKey.get(p.key)))
    const canHighlight = spec.better != null && spec.format !== 'text' && (spec.id !== 'weekPositionRank' || samePosition)
    const highlights = canHighlight
      ? highlightRow(values as (number | null)[], spec.better as 'higher' | 'lower')
      : values.map(() => null)
    return { id: spec.id, label: spec.label, format: spec.format, values, highlights }
  })
}
