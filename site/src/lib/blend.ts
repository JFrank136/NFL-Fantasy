// src/lib/blend.ts
//
// Pure calculation functions for the Rankings page. No Supabase, no React
// -- pages fetch rows and hand them to these functions. See
// docs/superpowers/specs/2026-09-17-site-redesign-shell-and-rankings-design.md
// for the product rationale behind each formula.

import { robustLinearFit, applyScale } from './regression'
import { weightsForPosition } from './consensusWeights'

// ---- ROS tab: blended value ----

export interface RosSourceRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  dsValue: number | null
  ceiling: number | null
}

export interface BooneRosRow {
  canonicalName: string
  position: string
  value: number | null
}

export interface BlendedRosRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  dsValue: number | null
  booneValue: number | null
  ceiling: number | null
  blendedValue: number | null
  overallRank: number | null
}

/**
 * Blends Draft Sharks' ds_value with Boone's matched ROS trade value.
 * Boone's scale is fit onto Draft Sharks' scale (via the existing
 * robustLinearFit/applyScale pair) using players present in both sources,
 * then the two are averaged 50/50. Players present in only one source use
 * that source's value unblended. Result is ranked cross-position by
 * blendedValue, descending (confirmed with Jared: "Overall rank" is a
 * single ranking across all positions, not per-position).
 */
export function blendRosValues(
  dsRows: RosSourceRow[],
  booneRows: BooneRosRow[],
): BlendedRosRow[] {
  const dsMap = new Map(dsRows.map(r => [r.canonicalName, r]))
  const booneMap = new Map(booneRows.map(r => [r.canonicalName, r]))

  const overlapping: { x: number; y: number }[] = []
  dsMap.forEach((ds, name) => {
    const boone = booneMap.get(name)
    if (ds.dsValue != null && boone?.value != null) {
      overlapping.push({ x: boone.value, y: ds.dsValue })
    }
  })
  const { a, b } = robustLinearFit(overlapping.map(p => p.x), overlapping.map(p => p.y))

  const allNames = new Set<string>([...dsMap.keys(), ...booneMap.keys()])
  const rows: BlendedRosRow[] = []
  allNames.forEach(name => {
    const ds = dsMap.get(name)
    const boone = booneMap.get(name)
    const scaledBoone = boone?.value != null ? applyScale(a, b, boone.value) : null

    let blendedValue: number | null
    if (ds?.dsValue != null && scaledBoone != null) {
      blendedValue = (ds.dsValue + scaledBoone) / 2
    } else if (ds?.dsValue != null) {
      blendedValue = ds.dsValue
    } else {
      blendedValue = scaledBoone
    }

    rows.push({
      canonicalName: name,
      playerName: ds?.playerName ?? name,
      position: ds?.position ?? boone?.position ?? '',
      team: ds?.team ?? null,
      dsValue: ds?.dsValue ?? null,
      booneValue: boone?.value ?? null,
      ceiling: ds?.ceiling ?? null,
      blendedValue,
      overallRank: null,
    })
  })

  rows.sort((r1, r2) => {
    if (r1.blendedValue == null) return 1
    if (r2.blendedValue == null) return -1
    return r2.blendedValue - r1.blendedValue
  })
  rows.forEach((row, i) => {
    row.overallRank = row.blendedValue != null ? i + 1 : null
  })

  return rows
}

// ---- Weekly tab: aggregate rank ----

export interface WeeklySourceRanks {
  draftsharks: number | null
  boone: number | null
  smythe: number | null
}

/**
 * Weighted average of each source's position-rank, using
 * consensusWeights.ts. A source missing a rank for this player has its
 * weight redistributed proportionally across the sources that do have one
 * (rather than left out, which would silently under-weight the total).
 */
export function weightedAverageRank(position: string, ranks: WeeklySourceRanks): number | null {
  const weights = weightsForPosition(position)
  const entries = (['draftsharks', 'boone', 'smythe'] as const)
    .map(source => ({ source, rank: ranks[source], weight: weights[source] }))
    .filter((e): e is { source: keyof WeeklySourceRanks; rank: number; weight: number } => e.rank != null)

  if (entries.length === 0) return null
  const totalWeight = entries.reduce((sum, e) => sum + e.weight, 0)
  if (totalWeight === 0) return null

  return entries.reduce((sum, e) => sum + e.rank * (e.weight / totalWeight), 0)
}

export interface WeeklyPlayerInput {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  draftsharksRank: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
  opponent: string | null
}

export interface AggregatedWeeklyRow extends WeeklyPlayerInput {
  aggregateScore: number | null
  aggregateRank: number | null
}

/** Re-ranks weightedAverageRank's output within each position (ascending -- lower weighted rank score is better). */
export function aggregateWeeklyRanks(players: WeeklyPlayerInput[]): AggregatedWeeklyRow[] {
  const withScores: AggregatedWeeklyRow[] = players.map(p => ({
    ...p,
    aggregateScore: weightedAverageRank(p.position, {
      draftsharks: p.draftsharksRank,
      boone: p.booneRank,
      smythe: p.smytheRank,
    }),
    aggregateRank: null,
  }))

  const byPosition = new Map<string, AggregatedWeeklyRow[]>()
  withScores.forEach(row => {
    const list = byPosition.get(row.position) ?? []
    list.push(row)
    byPosition.set(row.position, list)
  })

  byPosition.forEach(list => {
    list.sort((r1, r2) => {
      if (r1.aggregateScore == null) return 1
      if (r2.aggregateScore == null) return -1
      return r1.aggregateScore - r2.aggregateScore
    })
    list.forEach((row, i) => {
      row.aggregateRank = row.aggregateScore != null ? i + 1 : null
    })
  })

  return withScores
}
