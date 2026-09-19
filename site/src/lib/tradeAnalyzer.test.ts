import { describe, it, expect } from 'vitest'
import { evaluateTrade, CONFIDENCE_THRESHOLDS } from './tradeAnalyzer'
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
