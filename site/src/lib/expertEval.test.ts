import { describe, expect, it } from 'vitest'
import { buildPositionEdges, buildSummary, buildTierAccuracy, evidenceLabel, expertsIn, weightHistory, type ScoreRow, type WeightRow } from './expertEval'

const sc = (week: number, source: string, metric: string, value: number, extra: Partial<ScoreRow> = {}): ScoreRow =>
  ({ season: 2026, week, source, position: 'ALL', tier: 'ALL', metric, value, n: 10, ...extra })

const wt = (week: number, source: string, weight: number, set: 'six' | 'three' = 'six'): WeightRow => ({
  season: 2026, week, weight_set: set, source, weight, equal_weight: 0.5, skill_mean: 0.2, skill_sd: 0.4,
  p_better: 0.7, weeks_n: week - 1, raw_mean: 0.3, reason: 'tilt',
})

describe('expertEval builders', () => {
  it('summarises evidence per expert and takes weights from the latest week, with the prior week for change', () => {
    const scores = [sc(1, 'boone', 'edge_regret', 1), sc(2, 'boone', 'edge_regret', 3), sc(1, 'smythe', 'edge_regret', -1), sc(2, 'smythe', 'edge_regret', -3)]
    const weights = [wt(2, 'boone', 0.55), wt(2, 'smythe', 0.45), wt(3, 'boone', 0.6), wt(3, 'smythe', 0.4), wt(3, 'boone', 0.7, 'three')]
    const rows = buildSummary(scores, weights)
    const boone = rows.find(r => r.source === 'boone')!
    expect(boone.weeks).toBe(2)
    expect(boone.avgEdge).toBe(2)
    expect(boone.weight).toBe(0.6)
    expect(boone.prevWeight).toBe(0.55)
    expect(boone.threeWeight).toBe(0.7)
    expect(rows.find(r => r.source === 'smythe')!.avgEdge).toBe(-2)
  })

  it('includes a newly added source without code changes', () => {
    expect(expertsIn([{ source: 'winks' }, { source: 'newguy' }, { source: 'boone' }, { source: 'field' }])).toEqual(['boone', 'winks', 'newguy'])
  })

  it('pools tier accuracy weighted by pair counts', () => {
    const scores = [
      sc(1, 'boone', 'pair_acc', 0.6, { tier: 'T1', n: 30 }),
      sc(2, 'boone', 'pair_acc', 0.5, { tier: 'T1', n: 10 }),
    ]
    const t1 = buildTierAccuracy(scores)[0].byTier.T1!
    expect(t1.pairs).toBe(40)
    expect(t1.acc).toBeCloseTo(0.575)
  })

  it('averages component edges by position and leaves untouched components null', () => {
    const scores = [sc(1, 'boone', 'edge_regret', 0.5, { position: 'RB' }), sc(2, 'boone', 'edge_regret', 1.5, { position: 'RB' })]
    const row = buildPositionEdges(scores)[0]
    expect(row.byPos.RB).toEqual({ mean: 1, n: 2 })
    expect(row.byPos.QB).toBeNull()
  })

  it('weight history exposes values by source and week', () => {
    const g = weightHistory([wt(1, 'boone', 0.5), wt(2, 'boone', 0.6)])
    expect(g.weeks.map(w => w.week)).toEqual([1, 2])
    expect(g.value('boone', 2026, 2)).toBe(0.6)
    expect(g.value('boone', 2026, 3)).toBeNull()
  })

  it('does not over-claim early or ambiguous evidence', () => {
    expect(evidenceLabel(3, 0.99)).toBe('Too early')
    expect(evidenceLabel(9, 0.9)).toBe('Likely above field')
    expect(evidenceLabel(9, 0.5)).toBe('Not distinguishable')
    expect(evidenceLabel(9, 0.1)).toBe('Likely below field')
  })
})
