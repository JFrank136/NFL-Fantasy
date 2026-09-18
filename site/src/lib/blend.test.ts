import { describe, it, expect } from 'vitest'
import { blendRosValues, type RosSourceRow, type BooneRosRow } from './blend'
import { weightedAverageRank, aggregateWeeklyRanks, type WeeklyPlayerInput } from './blend'

describe('weightedAverageRank', () => {
  it('averages three sources using default (non-QB) weights', () => {
    // default weights: draftsharks 0.50, boone 0.30, smythe 0.20
    // ranks: DS=2, Boone=4, Smythe=3 -> 2*.5 + 4*.3 + 3*.2 = 1 + 1.2 + 0.6 = 2.8
    const result = weightedAverageRank('RB', { draftsharks: 2, boone: 4, smythe: 3 })
    expect(result).toBeCloseTo(2.8, 5)
  })

  it('uses QB weights for QB position', () => {
    // QB weights: draftsharks 0.40, boone 0.40, smythe 0.20
    // ranks: DS=1, Boone=2, Smythe=1 -> 1*.4 + 2*.4 + 1*.2 = 0.4 + 0.8 + 0.2 = 1.4
    const result = weightedAverageRank('QB', { draftsharks: 1, boone: 2, smythe: 1 })
    expect(result).toBeCloseTo(1.4, 5)
  })

  it('redistributes weight proportionally when a source is missing', () => {
    // default weights, smythe missing: DS=2 (0.5), Boone=4 (0.3), remaining
    // weight normalized over {0.5, 0.3} -> DS effective 0.625, Boone 0.375
    // 2*0.625 + 4*0.375 = 1.25 + 1.5 = 2.75
    const result = weightedAverageRank('RB', { draftsharks: 2, boone: 4, smythe: null })
    expect(result).toBeCloseTo(2.75, 5)
  })

  it('returns null when no source has a rank', () => {
    const result = weightedAverageRank('RB', { draftsharks: null, boone: null, smythe: null })
    expect(result).toBeNull()
  })

  it('falls back to CONSENSUS_WEIGHTS.default for a position not in the map', () => {
    // 'FLEX' has no entry in CONSENSUS_WEIGHTS, so weightsForPosition should
    // fall back to default weights: draftsharks 0.50, boone 0.30, smythe 0.20
    // ranks: DS=1, Boone=5, Smythe=3 -> 1*.5 + 5*.3 + 3*.2 = 0.5 + 1.5 + 0.6 = 2.6
    const result = weightedAverageRank('FLEX', { draftsharks: 1, boone: 5, smythe: 3 })
    expect(result).toBeCloseTo(2.6, 5)
  })
})

describe('aggregateWeeklyRanks', () => {
  it('re-ranks players within position by weighted score, best score = rank 1', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'a', playerName: 'A', position: 'RB', team: 'BUF', draftsharksRank: 3, booneRank: 3, smytheRank: 3, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'b', playerName: 'B', position: 'RB', team: 'MIA', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'c', playerName: 'C', position: 'RB', team: 'NYJ', draftsharksRank: 2, booneRank: 2, smytheRank: 2, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ A: 3, B: 1, C: 2 })
  })

  it('ranks positions independently', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'qb1', playerName: 'QB1', position: 'QB', team: 'BUF', draftsharksRank: 5, booneRank: 5, smytheRank: 5, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'rb1', playerName: 'RB1', position: 'RB', team: 'MIA', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ QB1: 1, RB1: 1 })
  })

  it('gives players missing from every source a null rank, sorted last', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'a', playerName: 'A', position: 'RB', team: 'BUF', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'b', playerName: 'B', position: 'RB', team: 'MIA', draftsharksRank: null, booneRank: null, smytheRank: null, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ A: 1, B: null })
  })
})

describe('blendRosValues', () => {
  it('blends overlapping players 50/50 after fitting Boone onto the DS scale', () => {
    // Boone's scale is roughly 2x Draft Sharks' in this fixture, so the fit
    // should scale boone values close to ds values before blending.
    const ds: RosSourceRow[] = [
      { canonicalName: 'p1', playerName: 'P1', position: 'RB', team: 'BUF', dsValue: 50, ceiling: 20 },
      { canonicalName: 'p2', playerName: 'P2', position: 'RB', team: 'MIA', dsValue: 40, ceiling: 18 },
      { canonicalName: 'p3', playerName: 'P3', position: 'RB', team: 'NYJ', dsValue: 30, ceiling: 16 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'p1', position: 'RB', value: 100 },
      { canonicalName: 'p2', position: 'RB', value: 80 },
      { canonicalName: 'p3', position: 'RB', value: 60 },
    ]
    const result = blendRosValues(ds, boone)
    const p1 = result.find(r => r.canonicalName === 'p1')!
    expect(p1.dsValue).toBe(50)
    expect(p1.booneValue).toBe(100)
    // After fitting boone (100/80/60) onto ds (50/40/30) the scaled boone
    // value for p1 should land close to 50, so the blend stays close to 50.
    expect(p1.blendedValue).not.toBeNull()
    expect(p1.blendedValue!).toBeGreaterThan(40)
    expect(p1.blendedValue!).toBeLessThan(60)
  })

  it('falls back to the single available value when a player is only in one source', () => {
    const ds: RosSourceRow[] = [
      { canonicalName: 'ds-only', playerName: 'DS Only', position: 'WR', team: 'BUF', dsValue: 70, ceiling: 25 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'boone-only', position: 'WR', value: 90 },
    ]
    const result = blendRosValues(ds, boone)
    const dsOnly = result.find(r => r.canonicalName === 'ds-only')!
    const booneOnly = result.find(r => r.canonicalName === 'boone-only')!
    expect(dsOnly.blendedValue).toBe(70)
    expect(booneOnly.blendedValue).toBe(90)
  })

  it('ranks cross-position by blended value, descending', () => {
    const ds: RosSourceRow[] = [
      { canonicalName: 'qb1', playerName: 'QB1', position: 'QB', team: 'BUF', dsValue: 90, ceiling: 30 },
      { canonicalName: 'rb1', playerName: 'RB1', position: 'RB', team: 'MIA', dsValue: 95, ceiling: 30 },
    ]
    const boone: BooneRosRow[] = []
    const result = blendRosValues(ds, boone)
    const byName = Object.fromEntries(result.map(r => [r.canonicalName, r.overallRank]))
    expect(byName).toEqual({ rb1: 1, qb1: 2 })
  })

  it('returns an empty array when both sources are empty', () => {
    const result = blendRosValues([], [])
    expect(result).toEqual([])
  })
})
