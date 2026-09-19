// src/lib/blend.ts
//
// Pure calculation functions for the Rankings page. No Supabase, no React
// -- pages fetch rows and hand them to these functions. See
// docs/superpowers/specs/2026-09-17-site-redesign-shell-and-rankings-design.md
// for the product rationale behind each formula.

import { robustLinearFit, applyScale } from './regression'
import { weightsForPosition } from './consensusWeights'

/**
 * Sources don't agree on defense's position code (Draft Sharks: "DEF",
 * Boone/Smyth: "DST") -- callers that join/group across sources by
 * (canonicalName, position) must normalize first, or the same team's
 * defense silently fails to merge across sources. Also used to guard
 * against the opposite failure: two DIFFERENT real people sharing a name
 * (e.g. WR Justin Jefferson vs. LB Justin Jefferson) getting merged into
 * one row just because canonical_name ignores position -- confirmed live
 * 2026-09-18. Joining on (canonicalName, normalizedPosition) instead of
 * canonicalName alone fixes both at once: same-position name collisions
 * stay separate, cross-labeled same-team defenses still merge.
 */
export function normalizePosition(position: string): string {
  return position === 'DEF' ? 'DST' : position
}

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
  /** Boone's value mapped onto the Draft Sharks scale (the same fit the blend uses). */
  booneScaled: number | null
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
/** (canonicalName, normalizedPosition) -- see normalizePosition for why
 * canonicalName alone isn't a safe join/group/React-key identity: two
 * different real people can share a canonical_name (e.g. WR Justin
 * Jefferson vs. LB Justin Jefferson). Exported so callers building their
 * own lookups against BlendedRosRow output (React keys, snapshot-to-
 * snapshot comparisons) use the same safe identity instead of bare
 * canonicalName. */
export function identityKey(canonicalName: string, position: string): string {
  return `${canonicalName}::${normalizePosition(position)}`
}

export function blendRosValues(
  dsRows: RosSourceRow[],
  booneRows: BooneRosRow[],
): BlendedRosRow[] {
  const dsMap = new Map(dsRows.map(r => [identityKey(r.canonicalName, r.position), r]))
  const booneMap = new Map(booneRows.map(r => [identityKey(r.canonicalName, r.position), r]))

  const overlapping: { x: number; y: number }[] = []
  dsMap.forEach((ds, key) => {
    const boone = booneMap.get(key)
    if (ds.dsValue != null && boone?.value != null) {
      overlapping.push({ x: boone.value, y: ds.dsValue })
    }
  })
  const { a, b } = robustLinearFit(overlapping.map(p => p.x), overlapping.map(p => p.y))

  const allKeys = new Set<string>([...dsMap.keys(), ...booneMap.keys()])
  const rows: BlendedRosRow[] = []
  allKeys.forEach(key => {
    const ds = dsMap.get(key)
    const boone = booneMap.get(key)
    const scaledBoone = boone?.value != null ? applyScale(a, b, boone.value) : null

    let blendedValue: number | null
    if (ds?.dsValue != null && scaledBoone != null) {
      blendedValue = (ds.dsValue + scaledBoone) / 2
    } else if (ds?.dsValue != null) {
      blendedValue = ds.dsValue
    } else {
      blendedValue = scaledBoone
    }

    const canonicalName = ds?.canonicalName ?? boone?.canonicalName ?? key
    rows.push({
      canonicalName,
      playerName: ds?.playerName ?? canonicalName,
      position: normalizePosition(ds?.position ?? boone?.position ?? ''),
      team: ds?.team ?? null,
      dsValue: ds?.dsValue ?? null,
      booneValue: boone?.value ?? null,
      booneScaled: scaledBoone,
      ceiling: ds?.ceiling ?? null,
      blendedValue,
      overallRank: null,
    })
  })

  rows.sort((r1, r2) => {
    if (r1.blendedValue == null && r2.blendedValue == null) return 0
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
  /**
   * Draft Sharks' rank exactly as published: an OVERALL rank across
   * everything it returns for the week, IDP/K/DST included. Week 2 2026 RBs
   * spanned 3-836 and WRs 10-870 while Boone/Smyth (Yahoo's FLX query) ran
   * 1-~155. Kept raw because the Rankings page displays it; the blend uses
   * `draftsharksScaledRank` instead. See rescaleDraftSharksRanks.
   */
  draftsharksRank: number | null
  /**
   * `draftsharksRank` re-ranked within the RB/WR/TE (FLEX) or QB group, so
   * it is on the same scale as Boone/Smyth. Set by rescaleDraftSharksRanks;
   * optional so callers that never rescale still type-check.
   */
  draftsharksScaledRank?: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
  opponent: string | null
  /**
   * The player's bye WEEK number as stored in `in_season_rankings_latest.bye`
   * (not a boolean). Optional because not every source row carries one.
   * Callers compare it against the week being displayed -- an empty
   * `opponent` is the other bye signal, and sources don't agree on which
   * they populate.
   */
  byeWeek?: number | null
}

export interface AggregatedWeeklyRow extends WeeklyPlayerInput {
  aggregateScore: number | null
  aggregateRank: number | null
}

/** RB/WR/TE share one scale; every other position is ranked against itself. */
const FLEX_SCALE_POSITIONS = ['RB', 'WR', 'TE']
const scaleGroupOf = (position: string) =>
  FLEX_SCALE_POSITIONS.includes(position) ? 'FLEX' : position

/**
 * Puts Draft Sharks' weekly rank on the same scale as Boone's and Smyth's
 * before they are averaged together.
 *
 * Draft Sharks publishes ONE overall weekly rank covering every player it
 * returns -- IDP, kickers and defenses included -- so a mid-range RB can sit
 * at 300 while Boone and Smyth, who rank within Yahoo's FLX (RB/WR/TE) and QB
 * groups, have that same player near 20. Averaging those raw numbers let
 * Draft Sharks' magnitude decide almost every score at weight .5, and a
 * player with no Draft Sharks row had that weight redistributed onto its much
 * smaller Boone/Smyth ranks, vaulting it many FLEX places above identical
 * peers (and opening fake 100+ point gaps that read as "High" confidence).
 *
 * Re-ranking within the FLEX and QB groups removes the magnitude difference
 * while preserving Draft Sharks' ordering, which is the part of its opinion
 * the blend actually wants. Ties share a rank (competition ranking: 1, 1, 3).
 * Pure: returns new objects and never mutates the input.
 *
 * Bye-week players stay in the ranking. They sort to wherever Draft Sharks
 * put them and are excluded downstream (buildWeeklyPool / computeFlexRanks),
 * so dropping them here would only shift everyone below them by one without
 * changing any comparison that is actually made.
 */
export function rescaleDraftSharksRanks<T extends WeeklyPlayerInput>(players: T[]): T[] {
  const rawByGroup = new Map<string, number[]>()
  players.forEach(p => {
    if (p.draftsharksRank == null) return
    const group = scaleGroupOf(p.position)
    const list = rawByGroup.get(group) ?? []
    list.push(p.draftsharksRank)
    rawByGroup.set(group, list)
  })

  return players.map(p => {
    if (p.draftsharksRank == null) return { ...p, draftsharksScaledRank: null }
    const peers = rawByGroup.get(scaleGroupOf(p.position)) as number[]
    const better = peers.filter(r => r < (p.draftsharksRank as number)).length
    return { ...p, draftsharksScaledRank: better + 1 }
  })
}

/** Re-ranks weightedAverageRank's output within each position (ascending -- lower weighted rank score is better). */
export function aggregateWeeklyRanks(players: WeeklyPlayerInput[]): AggregatedWeeklyRow[] {
  const withScores: AggregatedWeeklyRow[] = players.map(p => ({
    ...p,
    aggregateScore: weightedAverageRank(p.position, {
      // Falls back to the raw rank when nothing has been rescaled, so callers
      // that skip rescaleDraftSharksRanks keep their previous behaviour.
      draftsharks: p.draftsharksScaledRank ?? p.draftsharksRank,
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
      if (r1.aggregateScore == null && r2.aggregateScore == null) return 0
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
