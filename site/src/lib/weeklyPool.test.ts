import { describe, it, expect } from 'vitest'
import { computeFlexRanks, buildWeeklyPool, formatOpponent } from './weeklyPool'
import type { AggregatedWeeklyRow } from './blend'

function row(
  name: string,
  position: string,
  score: number | null,
  opponent: string | null = '@BUF',
  extra: Partial<AggregatedWeeklyRow> = {},
): AggregatedWeeklyRow {
  return {
    canonicalName: name, playerName: name, position, team: 'XXX',
    draftsharksRank: null, booneRank: null, smytheRank: null,
    dsProjection: null, dsFloor: null, dsCeiling: null,
    opponent, aggregateScore: score, aggregateRank: null, ...extra,
  }
}

describe('computeFlexRanks', () => {
  it('ranks RB/WR/TE together by weighted score, lowest score = rank 1', () => {
    const ranks = computeFlexRanks([row('te', 'TE', 9), row('rb', 'RB', 4), row('wr', 'WR', 2)], null)
    expect(ranks.get('wr::WR')).toBe(1)
    expect(ranks.get('rb::RB')).toBe(2)
    expect(ranks.get('te::TE')).toBe(3)
  })

  it('excludes QBs, bye-week players and unscored players', () => {
    const ranks = computeFlexRanks([
      row('qb', 'QB', 1),
      row('bye', 'RB', 0.5, null),
      row('none', 'WR', null),
      row('rb', 'RB', 4),
    ], null)
    expect(ranks.has('qb::QB')).toBe(false)
    expect(ranks.has('bye::RB')).toBe(false)
    expect(ranks.has('none::WR')).toBe(false)
    expect(ranks.get('rb::RB')).toBe(1)
  })

  it('excludes a player whose stored bye week is this week even with an opponent string', () => {
    const ranks = computeFlexRanks([
      row('onbye', 'RB', 1, '@BUF', { byeWeek: 7 }),
      row('rb', 'RB', 4, '@BUF', { byeWeek: 9 }),
    ], 7)
    expect(ranks.has('onbye::RB')).toBe(false)
    expect(ranks.get('rb::RB')).toBe(1)
  })

  it('gives tied scores the same rank', () => {
    const ranks = computeFlexRanks([row('a', 'RB', 5), row('b', 'WR', 5), row('c', 'TE', 6)], null)
    expect(ranks.get('a::RB')).toBe(1)
    expect(ranks.get('b::WR')).toBe(1)
    expect(ranks.get('c::TE')).toBe(3)
  })
})

describe('buildWeeklyPool', () => {
  it('keeps only QB/RB/WR/TE, carries FLEX rank, and flags byes', () => {
    const pool = buildWeeklyPool([
      row('rb', 'RB', 4, '@BUF', { aggregateRank: 2, draftsharksRank: 7, booneRank: 5, smytheRank: 6 }),
      row('k', 'K', 3),
      row('bye', 'WR', 2, null),
      row('qb', 'QB', 1),
    ], null)
    expect(pool.map(p => p.canonicalName).sort()).toEqual(['bye', 'qb', 'rb'])
    const rb = pool.find(p => p.canonicalName === 'rb')!
    expect(rb).toMatchObject({ key: 'rb::RB', flexRank: 1, positionRank: 2, dsRank: 7, booneRank: 5, smytheRank: 6, isBye: false })
    expect(pool.find(p => p.canonicalName === 'bye')).toMatchObject({ isBye: true, flexRank: null })
    expect(pool.find(p => p.canonicalName === 'qb')!.flexRank).toBeNull()
  })

  it('flags a bye from the stored bye column when it matches the current week', () => {
    const pool = buildWeeklyPool([
      row('onbye', 'RB', 1, 'vs. DET', { byeWeek: 7 }),
      row('playing', 'RB', 4, '@BUF', { byeWeek: 9 }),
    ], 7)
    expect(pool.find(p => p.canonicalName === 'onbye')).toMatchObject({ isBye: true, flexRank: null })
    expect(pool.find(p => p.canonicalName === 'playing')).toMatchObject({ isBye: false, flexRank: 1 })
  })

  it('does not treat a non-matching stored bye week as a bye', () => {
    const pool = buildWeeklyPool([row('a', 'RB', 1, '@BUF', { byeWeek: 12 })], 7)
    expect(pool[0].isBye).toBe(false)
  })
})

describe('formatOpponent', () => {
  it('formats away, home and bye', () => {
    expect(formatOpponent('@KC')).toBe('@KC')
    expect(formatOpponent('at IND')).toBe('@IND')
    expect(formatOpponent('NO')).toBe('vs NO')
    expect(formatOpponent(null)).toBe('BYE')
    expect(formatOpponent('')).toBe('BYE')
  })

  it("does not double up Yahoo's own 'vs.' prefix", () => {
    expect(formatOpponent('vs. DET')).toBe('vs DET')
    expect(formatOpponent('vs DET')).toBe('vs DET')
    expect(formatOpponent('VS DET')).toBe('vs DET')
  })
})
