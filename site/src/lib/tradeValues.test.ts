import { describe, it, expect } from 'vitest'
import { valueForScoring, pivotTradeValues, sourcesWithData, type TradeValueSourceRow } from './tradeValues'

function row(overrides: Partial<TradeValueSourceRow>): TradeValueSourceRow {
  return {
    source: 'boone',
    playerName: 'Test Player',
    canonicalName: 'test player',
    team: null,
    position: 'RB',
    valueCol1Label: 'HALF',
    valueCol1: 100,
    valueCol2Label: 'PPR',
    valueCol2: 120,
    ...overrides,
  }
}

describe('valueForScoring', () => {
  it('picks the HALF-labeled column for half-ppr', () => {
    const r = row({ valueCol1Label: 'HALF', valueCol1: 100, valueCol2Label: 'PPR', valueCol2: 120 })
    expect(valueForScoring(r, 'half-ppr')).toBe(100)
    expect(valueForScoring(r, 'ppr')).toBe(120)
  })

  it('handles USA Today style HALF/FULL labels', () => {
    const r = row({ valueCol1Label: 'HALF', valueCol1: 50, valueCol2Label: 'FULL', valueCol2: 60 })
    expect(valueForScoring(r, 'half-ppr')).toBe(50)
    expect(valueForScoring(r, 'ppr')).toBe(60)
  })

  it('returns null for a scoring the source does not publish (RSJ: PPR only)', () => {
    const r = row({ valueCol1Label: 'PPR', valueCol1: 200, valueCol2Label: 'N/A', valueCol2: null })
    expect(valueForScoring(r, 'ppr')).toBe(200)
    expect(valueForScoring(r, 'half-ppr')).toBeNull()
  })

  it('falls back to col1 for scoring-agnostic labels (QB 1QB/2QB league split)', () => {
    const r = row({ position: 'QB', valueCol1Label: '1QB', valueCol1: 9000, valueCol2Label: '2QB', valueCol2: 7000 })
    expect(valueForScoring(r, 'ppr')).toBe(9000)
    expect(valueForScoring(r, 'half-ppr')).toBe(9000)
  })

  it('falls back to col1 for a blended single value (FantasyPros VALUE)', () => {
    const r = row({ valueCol1Label: 'VALUE', valueCol1: 4500, valueCol2Label: 'N/A', valueCol2: null })
    expect(valueForScoring(r, 'ppr')).toBe(4500)
    expect(valueForScoring(r, 'half-ppr')).toBe(4500)
  })
})

describe('pivotTradeValues', () => {
  it('merges one player across sources into one row', () => {
    const rows: TradeValueSourceRow[] = [
      row({ source: 'boone', canonicalName: 'ceedee lamb', playerName: 'CeeDee Lamb', team: null, valueCol1: 100, valueCol2: 120 }),
      row({ source: 'cbs', canonicalName: 'ceedee lamb', playerName: 'CeeDee Lamb', team: 'DAL', valueCol1: 90, valueCol2: 110 }),
    ]
    const pivoted = pivotTradeValues(rows, 'ppr')
    expect(pivoted).toHaveLength(1)
    expect(pivoted[0].valuesBySource).toEqual({ boone: 120, cbs: 110 })
    expect(pivoted[0].normalizedScore).toBe(100) // only player -- top percentile in both source pools
  })

  it('backfills team from whichever source has it', () => {
    const rows: TradeValueSourceRow[] = [
      row({ source: 'boone', canonicalName: 'a', playerName: 'A', team: null }),
      row({ source: 'cbs', canonicalName: 'a', playerName: 'A', team: 'KC' }),
    ]
    const pivoted = pivotTradeValues(rows, 'ppr')
    expect(pivoted[0].team).toBe('KC')
  })

  it('ranks players by normalized score descending', () => {
    const rows: TradeValueSourceRow[] = [
      row({ source: 'boone', canonicalName: 'high', playerName: 'High', valueCol1: 900, valueCol2: 900 }),
      row({ source: 'boone', canonicalName: 'low', playerName: 'Low', valueCol1: 100, valueCol2: 100 }),
    ]
    const pivoted = pivotTradeValues(rows, 'ppr')
    expect(pivoted.map(r => r.playerName)).toEqual(['High', 'Low'])
    expect(pivoted[0].rank).toBe(1)
    expect(pivoted[1].rank).toBe(2)
  })

  it('excludes a source with no value for this scoring from the normalized score', () => {
    const rows: TradeValueSourceRow[] = [
      row({ source: 'boone', canonicalName: 'a', playerName: 'A', valueCol1Label: 'HALF', valueCol1: 100, valueCol2Label: 'PPR', valueCol2: 120 }),
      row({ source: 'rsj', canonicalName: 'a', playerName: 'A', valueCol1Label: 'PPR', valueCol1: 200, valueCol2Label: 'N/A', valueCol2: null }),
    ]
    const pivoted = pivotTradeValues(rows, 'half-ppr')
    expect(pivoted[0].valuesBySource).toEqual({ boone: 100, rsj: null })
    expect(pivoted[0].normalizedScore).toBe(100) // boone only -- rsj excluded, not averaged as 0
  })
})

describe('sourcesWithData', () => {
  it('drops a source that has no value anywhere for this scoring', () => {
    const rows: TradeValueSourceRow[] = [
      row({ source: 'boone', canonicalName: 'a', playerName: 'A', valueCol1Label: 'HALF', valueCol1: 100 }),
      row({ source: 'rsj', canonicalName: 'a', playerName: 'A', valueCol1Label: 'PPR', valueCol1: 200, valueCol2Label: 'N/A', valueCol2: null }),
    ]
    const pivoted = pivotTradeValues(rows, 'half-ppr')
    expect(sourcesWithData(pivoted)).toEqual(['boone'])
  })
})
