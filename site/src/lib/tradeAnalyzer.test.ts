import { describe, it, expect } from 'vitest'
import { evaluateTrade, compareBySource, buildExtraSourceValues, CONFIDENCE_THRESHOLDS } from './tradeAnalyzer'
import { identityKey } from './blend'
import type { TradeValueSourceRow } from './tradeValues'
import type { BlendedRosRow } from './blend'

function row(canonicalName: string, blendedValue: number | null, overrides: Partial<BlendedRosRow> = {}): BlendedRosRow {
  return {
    canonicalName,
    playerName: overrides.playerName ?? canonicalName,
    position: overrides.position ?? 'RB',
    team: overrides.team ?? null,
    dsValue: overrides.dsValue ?? blendedValue,
    booneValue: overrides.booneValue ?? blendedValue,
    booneScaled: overrides.booneScaled ?? blendedValue,
    ceiling: overrides.ceiling ?? null,
    blendedValue,
    overallRank: overrides.overallRank ?? null,
  }
}

describe('evaluateTrade', () => {
  it('reports a neutral state when either side is empty', () => {
    const result = evaluateTrade([row('a', 100)], [])
    expect(result.diff).toBeNull()
    expect(result.pctDiff).toBeNull()
    expect(result.preferredSide).toBeNull()
    expect(result.confidence).toBeNull()
    expect(result.sideA.totalValue).toBe(100)
    expect(result.sideB.totalValue).toBe(0)
  })

  it('sums blended value per side and picks the larger total as preferred', () => {
    const sideA = [row('a1', 60), row('a2', 60)]
    const sideB = [row('b1', 90)]
    const result = evaluateTrade(sideA, sideB)
    expect(result.sideA.totalValue).toBe(120)
    expect(result.sideB.totalValue).toBe(90)
    expect(result.diff).toBe(30)
    expect(result.preferredSide).toBe('A')
  })

  it('treats equal totals as an even trade with no preferred side', () => {
    const result = evaluateTrade([row('a', 100)], [row('b', 100)])
    expect(result.diff).toBe(0)
    expect(result.preferredSide).toBeNull()
    expect(result.summary).toMatch(/even trade/i)
  })

  it('ignores players with a null blended value when summing but still lists them', () => {
    const sideA = [row('a1', 100), row('a2', null)]
    const result = evaluateTrade(sideA, [row('b1', 100)])
    expect(result.sideA.totalValue).toBe(100)
    expect(result.sideA.players).toHaveLength(2)
    expect(result.diff).toBe(0)
  })

  it('identifies the best individual player on each side', () => {
    const sideA = [row('a1', 40), row('a2', 90)]
    const result = evaluateTrade(sideA, [row('b1', 50)])
    expect(result.sideA.bestPlayer?.canonicalName).toBe('a2')
  })

  it('classifies confidence using the exported thresholds', () => {
    // 100 vs 95 -> pctDiff = 5/100 = 0.05, below the "close" threshold
    const close = evaluateTrade([row('a', 100)], [row('b', 95)])
    expect(close.confidence).toBe('Close')
    expect(CONFIDENCE_THRESHOLDS.close).toBeGreaterThan(0.05)

    // 100 vs 85 -> pctDiff = 0.15, between close and medium thresholds
    const medium = evaluateTrade([row('a', 100)], [row('b', 85)])
    expect(medium.confidence).toBe('Medium')

    // 100 vs 50 -> pctDiff = 0.5, well past the medium threshold
    const high = evaluateTrade([row('a', 100)], [row('b', 50)])
    expect(high.confidence).toBe('High')
  })

  it('supports uneven player counts per side (e.g. 2-for-1)', () => {
    const sideA = [row('a1', 40), row('a2', 40)]
    const sideB = [row('b1', 100)]
    const result = evaluateTrade(sideA, sideB)
    expect(result.sideA.players).toHaveLength(2)
    expect(result.sideB.players).toHaveLength(1)
    expect(result.preferredSide).toBe('B')
  })
})

describe('side labels', () => {
  it('capitalizes Side A / Side B in the summary, including the best-player caveat', () => {
    // Side A wins on total (2x60 vs 100) but Side B holds the best individual player.
    const result = evaluateTrade([row('a1', 60), row('a2', 60)], [row('b1', 100, { playerName: 'Big Name' })])
    expect(result.summary).toContain('Side A gets more value')
    expect(result.summary).toContain('Side A still comes out ahead')
    expect(result.summary).not.toMatch(/side [ab]/)
  })
})

describe('compareBySource', () => {
  const extra = (rows: Array<[string, string, string, number | null]>) =>
    buildExtraSourceValues(
      rows.map(([source, canonicalName, position, value]): TradeValueSourceRow => ({
        source, canonicalName, playerName: canonicalName, position, team: null,
        valueCol1Label: 'PPR', valueCol1: value, valueCol2Label: 'N/A', valueCol2: null,
      })),
      'ppr',
    )

  it('totals DS and Boone per side and picks a winner per source', () => {
    const a = [row('a1', 50, { dsValue: 80, booneValue: 20 })]
    const b = [row('b1', 50, { dsValue: 60, booneValue: 40 })]
    const [ds, boone] = compareBySource(a, b)
    expect(ds).toMatchObject({ source: 'ds', totalA: 80, totalB: 60, winner: 'A' })
    expect(boone).toMatchObject({ source: 'boone', totalA: 20, totalB: 40, winner: 'B' })
  })

  it('discovers extra sources from the data and orders DS, Boone first', () => {
    const a = [row('a1', 50, { position: 'RB' })]
    const b = [row('b1', 50, { position: 'WR' })]
    const extras = extra([['rsj', 'a1', 'RB', 300], ['rsj', 'b1', 'WR', 200], ['cbs', 'a1', 'RB', 10]])
    expect(compareBySource(a, b, extras).map(s => s.source)).toEqual(['ds', 'boone', 'cbs', 'rsj'])
  })

  it('leaves the winner null when a side has no value in that source', () => {
    const extras = extra([['rsj', 'a1', 'RB', 300]])
    const rsj = compareBySource([row('a1', 50)], [row('b1', 50)], extras).find(s => s.source === 'rsj')!
    expect(rsj).toMatchObject({ totalA: 300, totalB: null, winner: null, pctDiff: null })
  })

  it('reports coverage when a side is missing a source value for one player', () => {
    const extras = extra([['rsj', 'a1', 'RB', 100], ['rsj', 'b1', 'RB', 50]])
    const rsj = compareBySource([row('a1', 1), row('a2', 1)], [row('b1', 1)], extras).find(s => s.source === 'rsj')!
    expect(rsj).toMatchObject({ valuedA: 1, sizeA: 2, valuedB: 1, sizeB: 1 })
  })

  it('does not let extra values shadow the DS/Boone values on the row', () => {
    const extras = extra([['ds', 'a1', 'RB', 999]])
    const ds = compareBySource([row('a1', 50, { dsValue: 70 })], [row('b1', 50, { dsValue: 10 })], extras)[0]
    expect(ds.totalA).toBe(70)
  })

  it('is empty when a side has no players (evaluateTrade neutral state)', () => {
    expect(evaluateTrade([row('a', 100)], []).sources).toEqual([])
  })
})

describe('buildExtraSourceValues', () => {
  it('skips excluded sources and uses the scoring-specific column', () => {
    const rows: TradeValueSourceRow[] = [
      { source: 'boone', canonicalName: 'x', playerName: 'X', position: 'RB', team: null, valueCol1Label: 'HALF', valueCol1: 1, valueCol2Label: 'PPR', valueCol2: 2 },
      { source: 'cbs', canonicalName: 'x', playerName: 'X', position: 'RB', team: null, valueCol1Label: 'HALF', valueCol1: 5, valueCol2Label: 'PPR', valueCol2: 7 },
    ]
    const out = buildExtraSourceValues(rows, 'ppr')
    expect(out.get(identityKey('x', 'RB'))).toEqual({ cbs: 7 })
  })
})
