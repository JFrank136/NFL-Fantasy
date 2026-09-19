import { describe, it, expect } from 'vitest'
import { blendRosValues, type RosSourceRow, type BooneRosRow } from './blend'
import { weightedAverageRank, aggregateWeeklyRanks, type WeeklyPlayerInput } from './blend'
import { normalizePosition, identityKey, rescaleDraftSharksRanks } from './blend'

function wp(name: string, position: string, extra: Partial<WeeklyPlayerInput> = {}): WeeklyPlayerInput {
  return {
    canonicalName: name, playerName: name.toUpperCase(), position, team: 'XXX',
    draftsharksRank: null, booneRank: null, smytheRank: null,
    dsProjection: null, dsFloor: null, dsCeiling: null, opponent: '@BUF', ...extra,
  }
}

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

  it('blends the rescaled Draft Sharks rank when one is present', () => {
    // Raw DS 500 would swamp Boone/Smyth 20/22 at weight .5; the scaled rank
    // is what belongs in the average.
    const [row] = aggregateWeeklyRanks([
      wp('a', 'RB', { draftsharksRank: 500, draftsharksScaledRank: 24, booneRank: 20, smytheRank: 22 }),
    ])
    // .5*24 + .3*20 + .2*22 = 22.4
    expect(row.aggregateScore).toBeCloseTo(22.4, 5)
    expect(row.draftsharksRank).toBe(500)
  })

  it('still uses the raw DS rank when nothing has been rescaled', () => {
    const [row] = aggregateWeeklyRanks([
      wp('a', 'RB', { draftsharksRank: 10, booneRank: 20, smytheRank: 30 }),
    ])
    expect(row.aggregateScore).toBeCloseTo(0.5 * 10 + 0.3 * 20 + 0.2 * 30, 5)
  })
})

describe('rescaleDraftSharksRanks', () => {
  it('re-ranks RB/WR/TE together as one FLEX group, 1-based and gap-free', () => {
    const out = rescaleDraftSharksRanks([
      wp('rb', 'RB', { draftsharksRank: 836 }),
      wp('wr', 'WR', { draftsharksRank: 10 }),
      wp('te', 'TE', { draftsharksRank: 300 }),
    ])
    const byName = Object.fromEntries(out.map(r => [r.canonicalName, r.draftsharksScaledRank]))
    expect(byName).toEqual({ wr: 1, te: 2, rb: 3 })
  })

  it('ranks QBs against QBs, not against the FLEX group', () => {
    const out = rescaleDraftSharksRanks([
      wp('qb1', 'QB', { draftsharksRank: 1 }),
      wp('qb2', 'QB', { draftsharksRank: 820 }),
      wp('rb1', 'RB', { draftsharksRank: 3 }),
      wp('rb2', 'RB', { draftsharksRank: 400 }),
    ])
    const byName = Object.fromEntries(out.map(r => [r.canonicalName, r.draftsharksScaledRank]))
    expect(byName).toEqual({ qb1: 1, qb2: 2, rb1: 1, rb2: 2 })
  })

  it('gives tied raw ranks the same scaled rank (competition ranking)', () => {
    const out = rescaleDraftSharksRanks([
      wp('a', 'RB', { draftsharksRank: 5 }),
      wp('b', 'WR', { draftsharksRank: 5 }),
      wp('c', 'TE', { draftsharksRank: 9 }),
    ])
    const byName = Object.fromEntries(out.map(r => [r.canonicalName, r.draftsharksScaledRank]))
    expect(byName).toEqual({ a: 1, b: 1, c: 3 })
  })

  it('leaves players without a Draft Sharks rank null and does not consume a slot', () => {
    const out = rescaleDraftSharksRanks([
      wp('none', 'RB', { draftsharksRank: null }),
      wp('a', 'RB', { draftsharksRank: 40 }),
      wp('b', 'WR', { draftsharksRank: 90 }),
    ])
    const byName = Object.fromEntries(out.map(r => [r.canonicalName, r.draftsharksScaledRank]))
    expect(byName).toEqual({ none: null, a: 1, b: 2 })
  })

  it('does not mutate its input', () => {
    const input = [wp('a', 'RB', { draftsharksRank: 40 })]
    const out = rescaleDraftSharksRanks(input)
    expect(input[0].draftsharksScaledRank).toBeUndefined()
    expect(out[0]).not.toBe(input[0])
    expect(out[0].draftsharksScaledRank).toBe(1)
  })

  it('keeps every other field intact', () => {
    const [out] = rescaleDraftSharksRanks([wp('a', 'RB', { draftsharksRank: 40, booneRank: 2, dsCeiling: 19 })])
    expect(out).toMatchObject({ canonicalName: 'a', position: 'RB', booneRank: 2, dsCeiling: 19, draftsharksRank: 40 })
  })
})

describe('Draft Sharks rescaling end to end', () => {
  // Draft Sharks' weekly rank is an OVERALL rank across everything it
  // publishes (IDP/K/DST included), so week-2 RB raw ranks span 3-836 while
  // Boone/Smyth's Yahoo FLX ranks span 1-~155. Blending them raw let DS
  // dominate, and redistributing its weight when a DS row was missing threw
  // players many FLEX spots. These two cases are the regressions.
  const flex = (name: string, extra: Partial<WeeklyPlayerInput>) => wp(name, 'RB', extra)

  it('stops a large raw DS rank from swamping close Boone/Smyth ranks', () => {
    // Filler so the two real players land near the top of the FLEX group.
    const players = [
      flex('a', { draftsharksRank: 500, booneRank: 20, smytheRank: 22 }),
      flex('b', { draftsharksRank: 520, booneRank: 21, smytheRank: 23 }),
    ]
    const rawScore = aggregateWeeklyRanks(players)[0].aggregateScore as number
    const scaledScore = aggregateWeeklyRanks(rescaleDraftSharksRanks(players))[0].aggregateScore as number
    expect(rawScore).toBeGreaterThan(200) // .5 * 500 dominates
    expect(scaledScore).toBeLessThan(25) // now in Boone/Smyth territory
  })

  it('no longer throws a DS-less player far from an otherwise identical peer', () => {
    // Both are RB20-ish to Boone and Smyth. Before rescaling, `withDs` carried
    // .5 * 300 = 150 while `noDs` had DS's weight redistributed onto its own
    // ranks (~20), a >100-point phantom gap that read as "High" confidence.
    const players = [
      flex('withDs', { draftsharksRank: 300, booneRank: 20, smytheRank: 20 }),
      flex('noDs', { draftsharksRank: null, booneRank: 20, smytheRank: 20 }),
      // Context so 300 scales to something sane rather than to rank 1.
      ...Array.from({ length: 24 }, (_, i) => flex(`filler${i}`, { draftsharksRank: i + 1, booneRank: i + 1, smytheRank: i + 1 })),
    ]
    const score = (rows: ReturnType<typeof aggregateWeeklyRanks>, name: string) =>
      rows.find(r => r.canonicalName === name)!.aggregateScore as number

    const raw = aggregateWeeklyRanks(players)
    expect(Math.abs(score(raw, 'withDs') - score(raw, 'noDs'))).toBeGreaterThan(100)

    const scaled = aggregateWeeklyRanks(rescaleDraftSharksRanks(players))
    expect(Math.abs(score(scaled, 'withDs') - score(scaled, 'noDs'))).toBeLessThan(5)
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

  it('does not merge two different real people who share a canonical_name at different positions', () => {
    // Confirmed live 2026-09-18: WR Justin Jefferson (MIN) and a real LB
    // named Justin Jefferson share a canonical_name -- joining on name alone
    // silently merged their data into one row.
    const ds: RosSourceRow[] = [
      { canonicalName: 'justin jefferson', playerName: 'Justin Jefferson', position: 'WR', team: 'MIN', dsValue: 90, ceiling: 30 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'justin jefferson', position: 'LB', value: 5 },
    ]
    const result = blendRosValues(ds, boone)
    expect(result).toHaveLength(2)
    const wr = result.find(r => r.position === 'WR')!
    const lb = result.find(r => r.position === 'LB')!
    expect(wr.dsValue).toBe(90)
    expect(wr.booneValue).toBeNull()
    expect(lb.booneValue).toBe(5)
    expect(lb.dsValue).toBeNull()
  })

  it('still merges the same team defense across sources spelling it DEF vs DST', () => {
    const ds: RosSourceRow[] = [
      { canonicalName: 'eagles', playerName: 'Philadelphia Eagles', position: 'DEF', team: 'PHI', dsValue: 40, ceiling: 10 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'eagles', position: 'DST', value: 50 },
    ]
    const result = blendRosValues(ds, boone)
    expect(result).toHaveLength(1)
    expect(result[0].position).toBe('DST')
    expect(result[0].dsValue).toBe(40)
    expect(result[0].booneValue).toBe(50)
  })
})

describe('normalizePosition', () => {
  it('maps DEF to DST and leaves everything else alone', () => {
    expect(normalizePosition('DEF')).toBe('DST')
    expect(normalizePosition('DST')).toBe('DST')
    expect(normalizePosition('WR')).toBe('WR')
  })
})

describe('identityKey', () => {
  it('treats DEF and DST as the same identity but keeps different positions distinct', () => {
    expect(identityKey('eagles', 'DEF')).toBe(identityKey('eagles', 'DST'))
    expect(identityKey('justin jefferson', 'WR')).not.toBe(identityKey('justin jefferson', 'LB'))
  })
})
