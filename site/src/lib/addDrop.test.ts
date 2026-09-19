import { describe, it, expect } from 'vitest'
import { analyzeAddDrop, addDropRows, ADD_DROP_THRESHOLDS } from './addDrop'
import type { ComparisonPlayer } from './playerComparison'
import type { WeeklyPlayer } from './weeklyPool'

function cp(name: string, overrides: Partial<ComparisonPlayer> = {}): ComparisonPlayer {
  return {
    key: `${name}::WR`, canonicalName: name, playerName: name, position: 'WR', team: 'XXX',
    blended: 50, ds: 50, boone: 50, ceiling: 20, overallRank: 10, positionRank: 5,
    trend: 0, sos: null, disagreement: null, ...overrides,
  }
}

function wp(key: string, overrides: Partial<WeeklyPlayer> = {}): WeeklyPlayer {
  return {
    key, canonicalName: key, playerName: key, position: 'WR', team: 'XXX', opponent: '@BUF', isBye: false,
    aggregateScore: 10, positionRank: 5, flexRank: 12, dsRank: 10, booneRank: 10, smytheRank: 10,
    dsProjection: 10, dsFloor: 5, dsCeiling: 18, ...overrides,
  }
}

describe('ADD_DROP_THRESHOLDS', () => {
  it('is pinned to the documented cutoffs', () => {
    expect(ADD_DROP_THRESHOLDS).toEqual({ yes: 5, marginal: 2 })
  })
})

describe('analyzeAddDrop', () => {
  it('needs at least one valued add and one valued drop', () => {
    expect(analyzeAddDrop([], [cp('d')]).status).toBe('insufficient')
    expect(analyzeAddDrop([cp('a')], []).status).toBe('insufficient')
    expect(analyzeAddDrop([cp('a', { blended: null })], [cp('d')]).status).toBe('insufficient')
  })

  it('compares the best add against the weakest drop', () => {
    const r = analyzeAddDrop(
      [cp('a1', { blended: 40 }), cp('a2', { blended: 60 })],
      [cp('d1', { blended: 30 }), cp('d2', { blended: 45 })],
    )
    expect(r.bestAdd?.canonicalName).toBe('a2')
    expect(r.dropTarget?.canonicalName).toBe('d1')
    expect(r.gap).toBe(30)
  })

  it('maps the gap to Yes / Marginal / No at the configured thresholds', () => {
    const verdict = (gap: number) => analyzeAddDrop([cp('a', { blended: 30 + gap })], [cp('d', { blended: 30 })]).verdict
    expect(verdict(ADD_DROP_THRESHOLDS.yes)).toBe('Yes')
    expect(verdict(ADD_DROP_THRESHOLDS.yes - 0.1)).toBe('Marginal')
    expect(verdict(ADD_DROP_THRESHOLDS.marginal)).toBe('Marginal')
    expect(verdict(ADD_DROP_THRESHOLDS.marginal - 0.1)).toBe('No')
    expect(verdict(-10)).toBe('No')
  })

  it('is not thrown off by float error in the gap (3.3 - 1.3 is 1.9999999999999998 raw)', () => {
    const r = analyzeAddDrop([cp('a', { blended: 3.3 })], [cp('d', { blended: 1.3 })])
    expect(r.gap).toBe(2)
    expect(r.verdict).toBe('Marginal')
  })

  it('adds an upside note when an add clearly out-ceilings the drop, even on a No', () => {
    const r = analyzeAddDrop(
      [cp('boom', { blended: 28, ceiling: 40 })],
      [cp('safe', { blended: 30, ceiling: 20 })],
    )
    expect(r.verdict).toBe('No')
    expect(r.upsideNote).toContain('boom has the higher ceiling than safe (40 vs 20)')
  })

  it('has no upside note without a clear ceiling edge or with missing ceilings', () => {
    expect(analyzeAddDrop([cp('a', { ceiling: 20.5 })], [cp('d', { ceiling: 20 })]).upsideNote).toBeNull()
    expect(analyzeAddDrop([cp('a', { ceiling: null })], [cp('d', { ceiling: 20 })]).upsideNote).toBeNull()
  })

  it('treats a ceiling edge of exactly 3 as clear despite float error (4.1 - 1.1 is 2.9999999999999996 raw)', () => {
    const r = analyzeAddDrop([cp('a', { ceiling: 4.1 })], [cp('d', { ceiling: 1.1 })])
    expect(r.upsideNote).toContain('a has the higher ceiling than d')
  })

  it('treats a drop-target ceiling edge of exactly 3 as a caveat despite float error', () => {
    const r = analyzeAddDrop([cp('a', { blended: 60, ceiling: 1.1 })], [cp('d', { blended: 30, ceiling: 4.1 })])
    expect(r.dropCaveat).toContain('d is the lowest ROS value')
  })

  it('caveats a drop suggestion whose ceiling beats the add', () => {
    const r = analyzeAddDrop(
      [cp('a', { blended: 60, ceiling: 20 })],
      [cp('lottery', { blended: 30, ceiling: 45 })],
    )
    expect(r.dropCaveat).toContain('lottery')
    expect(r.dropCaveat).toContain('higher ceiling than a')
  })

  it('has no caveat when the drop target has no ceiling edge', () => {
    expect(analyzeAddDrop([cp('a', { ceiling: 30 })], [cp('d', { ceiling: 20 })]).dropCaveat).toBeNull()
  })
})

describe('addDropRows', () => {
  it('highlights ROS value, ceiling and trend across all columns, add or drop', () => {
    const rows = addDropRows(
      [cp('a', { blended: 70, ceiling: 30, trend: 2 }), cp('d', { blended: 40, ceiling: 25, trend: -1 })],
      new Map(),
    )
    expect(rows.find(r => r.id === 'blended')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'ceiling')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'trend')!.highlights).toEqual(['best', 'worst'])
  })

  it('joins this-week outlook by key and shows a dash when there is none', () => {
    const rows = addDropRows(
      [cp('a'), cp('b')],
      new Map([['a::WR', wp('a::WR', { dsProjection: 14, flexRank: 8, positionRank: 3 })]]),
    )
    expect(rows.find(r => r.id === 'weekProjection')!.values).toEqual([14, null])
    expect(rows.find(r => r.id === 'weekFlexRank')!.values).toEqual([8, null])
    expect(rows.find(r => r.id === 'weekPositionRank')!.values).toEqual([3, null])
  })

  it('highlights weekly position rank only when every player shares a position', () => {
    const map = new Map([
      ['a::WR', wp('a::WR', { positionRank: 3 })],
      ['b::RB', wp('b::RB', { position: 'RB', positionRank: 9 })],
    ])
    const mixed = addDropRows([cp('a'), cp('b', { key: 'b::RB', position: 'RB' })], map)
    expect(mixed.find(r => r.id === 'weekPositionRank')!.highlights).toEqual([null, null])
  })

  it('shows SOS as text with no highlight', () => {
    const rows = addDropRows([cp('a', { sos: '-1.6%' }), cp('b', { sos: '+2.0%' })], new Map())
    const sos = rows.find(r => r.id === 'sos')!
    expect(sos.values).toEqual(['-1.6%', '+2.0%'])
    expect(sos.highlights).toEqual([null, null])
  })
})
