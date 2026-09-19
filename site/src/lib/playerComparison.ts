// src/lib/playerComparison.ts
//
// Pure calculation functions for the Player Comparison page (and, later,
// Start/Sit and Add/Drop, which reuse the same row-based comparison and
// best/worst highlighting). No Supabase, no React.

import { identityKey, type BlendedRosRow } from './blend'

export interface ComparisonPlayer {
  key: string
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  blended: number | null
  ds: number | null
  boone: number | null
  ceiling: number | null
  overallRank: number | null
  positionRank: number | null
  /** Blended ROS value change since the previous snapshot. */
  trend: number | null
  /** Draft Sharks' strength-of-schedule string, e.g. "-1.6%". Shown as-is. */
  sos: string | null
  /** Boone (on the DS scale) minus Draft Sharks. Positive = Boone higher. */
  disagreement: number | null
}

/**
 * Builds selectable comparison players from blended ROS rows. Position rank
 * is computed here (blend.ts only ranks overall) by blended value within
 * each position.
 */
export function buildComparisonPool(
  rows: BlendedRosRow[],
  trendByKey: Map<string, number | null>,
  sosByKey: Map<string, string | null>,
): ComparisonPlayer[] {
  const positionRanks = new Map<string, number>()
  const byPosition = new Map<string, BlendedRosRow[]>()
  rows.forEach(r => {
    if (r.blendedValue == null) return
    const list = byPosition.get(r.position) ?? []
    list.push(r)
    byPosition.set(r.position, list)
  })
  byPosition.forEach(list => {
    list.sort((a, b) => (b.blendedValue as number) - (a.blendedValue as number))
    list.forEach((r, i) => positionRanks.set(identityKey(r.canonicalName, r.position), i + 1))
  })

  return rows.map(r => {
    const key = identityKey(r.canonicalName, r.position)
    return {
      key,
      canonicalName: r.canonicalName,
      playerName: r.playerName,
      position: r.position,
      team: r.team,
      blended: r.blendedValue,
      ds: r.dsValue,
      boone: r.booneValue,
      ceiling: r.ceiling,
      overallRank: r.overallRank,
      positionRank: positionRanks.get(key) ?? null,
      trend: trendByKey.get(key) ?? null,
      sos: sosByKey.get(key) ?? null,
      disagreement: r.booneScaled != null && r.dsValue != null ? r.booneScaled - r.dsValue : null,
    }
  })
}

export type Highlight = 'best' | 'worst' | null
export type CellFormat = 'value' | 'rank' | 'signed' | 'text'

export interface ComparisonRow {
  id: string
  label: string
  format: CellFormat
  values: (number | string | null)[]
  highlights: Highlight[]
}

/**
 * Marks the best and worst cell in a row. Null values are skipped, and a
 * row where every present value is equal (or fewer than two are present)
 * gets no highlight -- there's nothing to distinguish. Ties for best/worst
 * are all marked.
 */
export function highlightRow(values: (number | null)[], better: 'higher' | 'lower'): Highlight[] {
  const present = values.filter((v): v is number => v != null)
  if (present.length < 2) return values.map(() => null)
  const max = Math.max(...present)
  const min = Math.min(...present)
  if (max === min) return values.map(() => null)
  const best = better === 'higher' ? max : min
  const worst = better === 'higher' ? min : max
  return values.map(v => (v == null ? null : v === best ? 'best' : v === worst ? 'worst' : null))
}

interface RowSpec {
  id: string
  label: string
  format: CellFormat
  /** null = show but never highlight (direction isn't clear-cut). */
  better: 'higher' | 'lower' | null
  pick: (p: ComparisonPlayer) => number | string | null
}

const ROW_SPECS: RowSpec[] = [
  { id: 'blended', label: 'Blended ROS value', format: 'value', better: 'higher', pick: p => p.blended },
  { id: 'ds', label: 'Draft Sharks ROS value', format: 'value', better: 'higher', pick: p => p.ds },
  { id: 'boone', label: 'Boone ROS value', format: 'value', better: 'higher', pick: p => p.boone },
  { id: 'ceiling', label: 'DS ceiling', format: 'value', better: 'higher', pick: p => p.ceiling },
  { id: 'overallRank', label: 'ROS rank', format: 'rank', better: 'lower', pick: p => p.overallRank },
  { id: 'positionRank', label: 'Position rank', format: 'rank', better: 'lower', pick: p => p.positionRank },
  { id: 'trend', label: 'ROS trend', format: 'signed', better: 'higher', pick: p => p.trend },
  // Direction of Draft Sharks' SOS percentage isn't documented, so it is
  // shown as context only, never highlighted.
  { id: 'sos', label: 'Strength of schedule', format: 'text', better: null, pick: p => p.sos },
  { id: 'disagreement', label: 'Boone vs DS', format: 'signed', better: null, pick: p => p.disagreement },
]

/** Row-based comparison (one row per stat, one column per player). */
export function comparisonRows(players: ComparisonPlayer[]): ComparisonRow[] {
  const samePosition = new Set(players.map(p => p.position)).size <= 1
  return ROW_SPECS.map(spec => {
    const values = players.map(spec.pick)
    // Position rank only means something between players at the same position.
    const canHighlight = spec.better != null && (spec.id !== 'positionRank' || samePosition)
    const highlights = canHighlight && spec.format !== 'text'
      ? highlightRow(values as (number | null)[], spec.better as 'higher' | 'lower')
      : values.map(() => null)
    return { id: spec.id, label: spec.label, format: spec.format, values, highlights }
  })
}

const round1 = (n: number) => Math.round(n * 10) / 10

/** 1-2 short sentences on the biggest differences. */
export function summarizeComparison(players: ComparisonPlayer[]): string {
  const valued = players.filter(p => p.blended != null)
  if (players.length < 2 || valued.length < 2) return 'Add at least two players to compare.'

  const byBlended = [...valued].sort((a, b) => (b.blended as number) - (a.blended as number))
  const top = byBlended[0]
  const next = byBlended[1]
  const lead = round1((top.blended as number) - (next.blended as number))
  const sentences = [
    lead === 0
      ? `${top.playerName} and ${next.playerName} are tied on blended ROS value.`
      : `${top.playerName} leads on blended ROS value, ${lead} ahead of ${next.playerName}.`,
  ]

  const withCeiling = players.filter(p => p.ceiling != null)
  if (withCeiling.length >= 2) {
    const ceilingLeader = [...withCeiling].sort((a, b) => (b.ceiling as number) - (a.ceiling as number))[0]
    if (ceilingLeader.key !== top.key) {
      sentences.push(`${ceilingLeader.playerName} has the highest ceiling.`)
      return sentences.join(' ')
    }
  }

  const withTrend = players.filter(p => p.trend != null && p.trend !== 0)
  if (withTrend.length > 0) {
    const mover = [...withTrend].sort((a, b) => Math.abs(b.trend as number) - Math.abs(a.trend as number))[0]
    const t = mover.trend as number
    sentences.push(`${mover.playerName} has moved the most recently (${t > 0 ? '+' : ''}${round1(t)}).`)
  }
  return sentences.join(' ')
}
