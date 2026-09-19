// src/lib/disagreement.ts
//
// Pure calculation functions for the Expert Disagreement page. Boone and
// Draft Sharks publish on different value scales, so gaps are measured with
// Boone mapped onto the Draft Sharks scale (BlendedRosRow.booneScaled, the
// same fit the blend uses) -- comparing raw values would mostly measure the
// scale difference.

import { identityKey, type BlendedRosRow } from './blend'
import type { MoverRow } from './movers'

/** A source counts as "flat" when its movement is smaller than this, in
 * Draft Sharks value units. Tunable, per the roadmap. */
export const FLAT_THRESHOLD = 1.5

/** Players ranked below this in BOTH sources are skipped. Deep-bench values
 * are noisy (Draft Sharks goes far negative for players nobody rosters), so
 * without a cutoff the biggest "disagreements" are all irrelevant. Tunable. */
export const RELEVANCE_RANK_CUTOFF = 150

export interface CurrentDisagreementRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  dsValue: number
  booneValue: number
  booneScaled: number
  /** Rank within each source's own ROS ranking (cross-position, 1 = best). */
  dsRank: number
  booneRank: number
  /** booneScaled - dsValue. Positive = Boone is higher on the player. */
  valueGap: number
}

function rankMap(rows: BlendedRosRow[], pick: (r: BlendedRosRow) => number | null): Map<string, number> {
  const ranked = rows
    .filter(r => pick(r) != null)
    .sort((a, b) => (pick(b) as number) - (pick(a) as number))
  return new Map(ranked.map((r, i) => [identityKey(r.canonicalName, r.position), i + 1]))
}

/** Players in both sources and relevant in at least one, largest absolute value gap first. */
export function currentDisagreements(rows: BlendedRosRow[]): CurrentDisagreementRow[] {
  const dsRanks = rankMap(rows, r => r.dsValue)
  const booneRanks = rankMap(rows, r => r.booneValue)

  const out: CurrentDisagreementRow[] = []
  for (const r of rows) {
    if (r.dsValue == null || r.booneValue == null || r.booneScaled == null) continue
    const key = identityKey(r.canonicalName, r.position)
    const dsRank = dsRanks.get(key) as number
    const booneRank = booneRanks.get(key) as number
    if (Math.min(dsRank, booneRank) > RELEVANCE_RANK_CUTOFF) continue
    out.push({
      canonicalName: r.canonicalName,
      playerName: r.playerName,
      position: r.position,
      team: r.team,
      dsValue: r.dsValue,
      booneValue: r.booneValue,
      booneScaled: r.booneScaled,
      dsRank,
      booneRank,
      valueGap: r.booneScaled - r.dsValue,
    })
  }
  return out.sort((a, b) => Math.abs(b.valueGap) - Math.abs(a.valueGap))
}

export interface DirectionDisagreementRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  /** Boone change, on the Draft Sharks scale. */
  booneChange: number
  dsChange: number
  /** |booneChange - dsChange| -- how far apart the two moved. */
  size: number
}

function direction(change: number): -1 | 0 | 1 {
  if (Math.abs(change) < FLAT_THRESHOLD) return 0
  return change > 0 ? 1 : -1
}

/**
 * Players where the two sources moved in different directions: one up and
 * the other down, or one moving while the other stayed flat. Both moving
 * the same way (or both flat) is not a disagreement -- that's already
 * covered by Movers & Fallers. Largest gap between the two changes first.
 */
export function directionDisagreements(dsMovers: MoverRow[], booneMovers: MoverRow[]): DirectionDisagreementRow[] {
  const boone = new Map(booneMovers.map(m => [identityKey(m.canonicalName, m.position), m]))

  const out: DirectionDisagreementRow[] = []
  for (const ds of dsMovers) {
    const b = boone.get(identityKey(ds.canonicalName, ds.position))
    if (!b || ds.change == null || b.change == null) continue
    if (direction(ds.change) === direction(b.change)) continue
    out.push({
      canonicalName: ds.canonicalName,
      playerName: ds.playerName,
      position: ds.position,
      team: ds.team,
      booneChange: b.change,
      dsChange: ds.change,
      size: Math.abs(b.change - ds.change),
    })
  }
  return out.sort((a, b) => b.size - a.size)
}
