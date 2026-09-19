import { describe, it, expect } from 'vitest'
import { buildComparisonPool, comparisonRows, highlightRow, summarizeComparison, type ComparisonPlayer } from './playerComparison'
import type { BlendedRosRow } from './blend'

function blended(name: string, position: string, value: number | null, extra: Partial<BlendedRosRow> = {}): BlendedRosRow {
  return {
    canonicalName: name, playerName: name, position, team: null,
    dsValue: value, booneValue: value, booneScaled: value, ceiling: null,
    blendedValue: value, overallRank: null, ...extra,
  }
}

function player(name: string, overrides: Partial<ComparisonPlayer> = {}): ComparisonPlayer {
  return {
    key: `${name}::WR`, canonicalName: name, playerName: name, position: 'WR', team: null,
    blended: 50, ds: 50, boone: 50, ceiling: null, overallRank: 10, positionRank: 5,
    trend: null, sos: null, disagreement: null, ...overrides,
  }
}

describe('buildComparisonPool', () => {
  it('computes position rank within each position by blended value', () => {
    const rows = [blended('wr1', 'WR', 90), blended('wr2', 'WR', 70), blended('rb1', 'RB', 60)]
    const pool = buildComparisonPool(rows, new Map(), new Map())
    const byName = Object.fromEntries(pool.map(p => [p.canonicalName, p.positionRank]))
    expect(byName).toEqual({ wr1: 1, wr2: 2, rb1: 1 })
  })

  it('joins trend and SOS by identity key and derives Boone-vs-DS disagreement', () => {
    const row = blended('a', 'WR', 50, { dsValue: 40, booneScaled: 55 })
    const key = 'a::WR'
    const [p] = buildComparisonPool([row], new Map([[key, 3.5]]), new Map([[key, '-1.6%']]))
    expect(p.trend).toBe(3.5)
    expect(p.sos).toBe('-1.6%')
    expect(p.disagreement).toBe(15)
  })
})

describe('highlightRow', () => {
  it('marks best and worst, direction-aware', () => {
    expect(highlightRow([10, 30, 20], 'higher')).toEqual(['worst', 'best', null])
    expect(highlightRow([10, 30, 20], 'lower')).toEqual(['best', 'worst', null])
  })

  it('skips nulls and marks nothing when values are equal or fewer than two are present', () => {
    expect(highlightRow([5, 5, 5], 'higher')).toEqual([null, null, null])
    expect(highlightRow([5, null], 'higher')).toEqual([null, null])
    expect(highlightRow([5, null, 9], 'higher')).toEqual(['worst', null, 'best'])
  })
})

describe('comparisonRows', () => {
  it('produces one column per player and highlights the higher blended value', () => {
    const rows = comparisonRows([player('a', { blended: 80 }), player('b', { blended: 60 })])
    const blendedRow = rows.find(r => r.id === 'blended')!
    expect(blendedRow.values).toEqual([80, 60])
    expect(blendedRow.highlights).toEqual(['best', 'worst'])
  })

  it('does not highlight position rank across different positions', () => {
    const rows = comparisonRows([player('a', { positionRank: 1 }), player('b', { position: 'RB', positionRank: 9 })])
    expect(rows.find(r => r.id === 'positionRank')!.highlights).toEqual([null, null])
  })

  it('never highlights strength of schedule', () => {
    const rows = comparisonRows([player('a', { sos: '3.0%' }), player('b', { sos: '-2.0%' })])
    expect(rows.find(r => r.id === 'sos')!.highlights).toEqual([null, null])
  })
})

describe('summarizeComparison', () => {
  it('names the blended leader and margin', () => {
    const s = summarizeComparison([player('a', { blended: 80 }), player('b', { blended: 60 })])
    expect(s).toContain('a leads on blended ROS value, 20 ahead of b')
  })

  it('calls out a different ceiling leader', () => {
    const s = summarizeComparison([player('a', { blended: 80, ceiling: 10 }), player('b', { blended: 60, ceiling: 30 })])
    expect(s).toContain('b has the highest ceiling')
  })

  it('asks for more players when fewer than two have values', () => {
    expect(summarizeComparison([player('a')])).toMatch(/at least two/i)
  })
})
