import { describe, it, expect } from 'vitest'
import { recommendStartSit, startSitRows, CONFIDENCE_THRESHOLDS } from './startSit'
import type { WeeklyPlayer } from './weeklyPool'

function wp(name: string, overrides: Partial<WeeklyPlayer> = {}): WeeklyPlayer {
  return {
    key: `${name}::RB`, canonicalName: name, playerName: name, position: 'RB', team: 'XXX',
    opponent: '@BUF', isBye: false, aggregateScore: 10, positionRank: 5, flexRank: 10,
    dsRank: 10, booneRank: 10, smytheRank: 10,
    dsProjection: 12, dsFloor: 6, dsCeiling: 20, ...overrides,
  }
}

describe('recommendStartSit', () => {
  it('starts the player with the lowest weighted score', () => {
    const a = wp('a', { aggregateScore: 4 })
    const b = wp('b', { aggregateScore: 12 })
    const rec = recommendStartSit([b, a])
    expect(rec.status).toBe('ok')
    expect(rec.starterKey).toBe('a::RB')
  })

  it('maps score gap to confidence at the configured thresholds', () => {
    const at = (gap: number) =>
      recommendStartSit([wp('a', { aggregateScore: 10 }), wp('b', { aggregateScore: 10 + gap })]).confidence
    expect(at(CONFIDENCE_THRESHOLDS.high)).toBe('High')
    expect(at(CONFIDENCE_THRESHOLDS.high - 0.1)).toBe('Medium')
    expect(at(CONFIDENCE_THRESHOLDS.medium)).toBe('Medium')
    expect(at(CONFIDENCE_THRESHOLDS.medium - 0.1)).toBe('Toss-up')
    expect(at(0)).toBe('Toss-up')
  })

  it('pins the confidence thresholds so retuning is a deliberate change', () => {
    expect(CONFIDENCE_THRESHOLDS).toEqual({ high: 5, medium: 2 })
  })

  it('is not thrown off by floating-point noise in the score gap', () => {
    const conf = (a: number, b: number) =>
      recommendStartSit([wp('a', { aggregateScore: a }), wp('b', { aggregateScore: b })]).confidence
    expect(conf(1.3, 3.3)).toBe('Medium') // raw gap is 1.9999999999999998
    expect(conf(1.1, 6.1)).toBe('High')
  })

  it('excludes bye-week players and says so', () => {
    const rec = recommendStartSit([
      wp('bye', { aggregateScore: 1, opponent: null, isBye: true }),
      wp('a', { aggregateScore: 8 }),
      wp('b', { aggregateScore: 9 }),
    ])
    expect(rec.starterKey).toBe('a::RB')
    expect(rec.note).toContain('bye')
  })

  it('needs at least two playable, ranked players', () => {
    expect(recommendStartSit([wp('a')]).status).toBe('insufficient')
    expect(recommendStartSit([wp('a'), wp('b', { aggregateScore: null })]).status).toBe('insufficient')
    expect(recommendStartSit([wp('a'), wp('b', { isBye: true, opponent: null })]).status).toBe('insufficient')
  })

  it('refuses to compare a QB with a non-QB', () => {
    const rec = recommendStartSit([
      wp('qb', { position: 'QB', key: 'qb::QB', aggregateScore: 3 }),
      wp('rb', { aggregateScore: 4 }),
    ])
    expect(rec.status).toBe('not-comparable')
    expect(rec.starterKey).toBeNull()
    expect(rec.note).toContain('QB')
  })

  it('allows RB/WR/TE to be compared together (FLEX) and QBs together', () => {
    expect(recommendStartSit([wp('rb'), wp('wr', { position: 'WR', key: 'wr::WR', aggregateScore: 9 })]).status).toBe('ok')
    expect(recommendStartSit([
      wp('q1', { position: 'QB', key: 'q1::QB' }),
      wp('q2', { position: 'QB', key: 'q2::QB', aggregateScore: 12 }),
    ]).status).toBe('ok')
  })

  it('reasons: notes when both sources rank the starter ahead', () => {
    const rec = recommendStartSit([
      wp('a', { aggregateScore: 4, dsRank: 3, booneRank: 4 }),
      wp('b', { aggregateScore: 9, dsRank: 8, booneRank: 9 }),
    ])
    expect(rec.reasons[0]).toContain('both Draft Sharks and Boone')
  })

  it('reasons: flags when the sources split', () => {
    const rec = recommendStartSit([
      wp('a', { aggregateScore: 8, dsRank: 3, booneRank: 12 }),
      wp('b', { aggregateScore: 9, dsRank: 9, booneRank: 5 }),
    ])
    expect(rec.reasons[0]).toContain('Sources split')
    expect(rec.reasons[0]).toContain('Draft Sharks favors a')
    expect(rec.reasons[0]).toContain('Boone favors b')
  })

  it('reasons: flags when both sources rank the runner-up ahead but the weighted score picks the starter', () => {
    const rec = recommendStartSit([
      wp('a', { aggregateScore: 5, dsRank: 9, booneRank: 9, smytheRank: 1 }),
      wp('b', { aggregateScore: 8, dsRank: 3, booneRank: 4, smytheRank: 20 }),
    ])
    expect(rec.starterKey).toBe('a::RB')
    expect(rec.reasons[0]).toContain('both rank b ahead')
    expect(rec.reasons[0]).toContain('weighted score favors a')
  })

  it('reasons: cites a big FLEX-rank gap even when position ranks look close', () => {
    const rec = recommendStartSit([
      wp('rb4', { aggregateScore: 4, positionRank: 4, flexRank: 4, dsRank: null, booneRank: null }),
      wp('rb6', { aggregateScore: 20, positionRank: 6, flexRank: 20, dsRank: null, booneRank: null }),
    ])
    expect(rec.reasons.join(' ')).toContain('FLEX rank #4 vs #20 for rb6')
  })

  it('reasons: mentions the runner-up having the higher ceiling', () => {
    const rec = recommendStartSit([
      wp('a', { aggregateScore: 4, dsCeiling: 15, dsRank: null, booneRank: null, flexRank: null }),
      wp('b', { aggregateScore: 6, dsCeiling: 25, dsRank: null, booneRank: null, flexRank: null }),
    ])
    expect(rec.reasons.join(' ')).toContain('b has the higher ceiling (25 vs 15)')
  })

  it('returns at most two reasons and always at least one', () => {
    const many = recommendStartSit([
      wp('a', { aggregateScore: 4, dsRank: 3, booneRank: 4, flexRank: 4, dsCeiling: 10 }),
      wp('b', { aggregateScore: 20, dsRank: 20, booneRank: 21, flexRank: 20, dsCeiling: 30 }),
    ])
    expect(many.reasons.length).toBe(2)
    const bare = recommendStartSit([
      wp('a', { aggregateScore: 4, dsRank: null, booneRank: null, flexRank: null, dsCeiling: null, dsProjection: null }),
      wp('b', { aggregateScore: 4.5, dsRank: null, booneRank: null, flexRank: null, dsCeiling: null, dsProjection: null }),
    ])
    expect(bare.reasons.length).toBe(1)
  })
})

describe('startSitRows', () => {
  it('builds one row per stat and highlights lower-is-better ranks and higher-is-better points', () => {
    const a = wp('a', { aggregateScore: 4, dsProjection: 15 })
    const b = wp('b', { aggregateScore: 9, dsProjection: 11 })
    const rows = startSitRows([a, b], new Map())
    const score = rows.find(r => r.id === 'score')!
    expect(score.highlights).toEqual(['best', 'worst'])
    const proj = rows.find(r => r.id === 'dsProjection')!
    expect(proj.highlights).toEqual(['best', 'worst'])
  })

  it('shows opponent as text and BYE for bye weeks, never highlighted', () => {
    const rows = startSitRows([wp('a', { opponent: '@KC' }), wp('b', { opponent: null, isBye: true })], new Map())
    const opp = rows.find(r => r.id === 'opponent')!
    expect(opp.values).toEqual(['@KC', 'BYE'])
    expect(opp.highlights).toEqual([null, null])
  })

  it('does not let a bye-week player affect highlights', () => {
    const rows = startSitRows([
      wp('a', { aggregateScore: 8 }),
      wp('b', { aggregateScore: 9 }),
      wp('bye', { aggregateScore: 1, isBye: true, opponent: null }),
    ], new Map())
    expect(rows.find(r => r.id === 'score')!.highlights).toEqual(['best', 'worst', null])
  })

  it('ignores a bye-week player of another position when deciding to highlight position rank', () => {
    const rows = startSitRows([
      wp('rb1', { positionRank: 3 }),
      wp('rb2', { positionRank: 8 }),
      wp('bye', { position: 'WR', key: 'bye::WR', positionRank: 1, isBye: true, opponent: null }),
    ], new Map())
    expect(rows.find(r => r.id === 'positionRank')!.highlights).toEqual(['best', 'worst', null])
  })

  it('highlights nothing scale-dependent when a QB is mixed with a non-QB', () => {
    const rows = startSitRows([
      wp('qb', { position: 'QB', key: 'qb::QB', aggregateScore: 3, dsRank: 2, booneRank: 2, smytheRank: 2, dsProjection: 22, dsFloor: 14, dsCeiling: 30 }),
      wp('rb', { aggregateScore: 9, dsRank: 40, booneRank: 41, smytheRank: 42, dsProjection: 11, dsFloor: 5, dsCeiling: 18 }),
    ], new Map())
    for (const id of ['score', 'dsRank', 'booneRank', 'smytheRank', 'dsProjection', 'dsFloor', 'dsCeiling']) {
      expect(rows.find(r => r.id === id)!.highlights, id).toEqual([null, null])
    }
  })

  it('still highlights score and projections across RB/WR (one FLEX scale)', () => {
    const rows = startSitRows([
      wp('rb', { aggregateScore: 4, dsRank: 5, booneRank: 5, smytheRank: 5, dsProjection: 15, dsFloor: 8, dsCeiling: 24 }),
      wp('wr', { position: 'WR', key: 'wr::WR', aggregateScore: 9, dsRank: 20, booneRank: 21, smytheRank: 22, dsProjection: 11, dsFloor: 5, dsCeiling: 18 }),
    ], new Map())
    expect(rows.find(r => r.id === 'score')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'dsProjection')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'dsFloor')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'dsCeiling')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'dsRank')!.highlights).toEqual(['best', 'worst'])
  })

  it('highlights position rank only when everyone shares a position; ROS is context only', () => {
    const mixed = startSitRows([wp('rb'), wp('wr', { position: 'WR', key: 'wr::WR', positionRank: 1 })], new Map())
    expect(mixed.find(r => r.id === 'positionRank')!.highlights).toEqual([null, null])
    const ros = startSitRows([wp('a'), wp('b')], new Map([['a::RB', 80], ['b::RB', 40]]))
    const rosRow = ros.find(r => r.id === 'ros')!
    expect(rosRow.values).toEqual([80, 40])
    expect(rosRow.highlights).toEqual([null, null])
  })
})
