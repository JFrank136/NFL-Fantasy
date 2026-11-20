import { describe, it, expect } from 'vitest'
import { dropStaleStragglers, onlyWeek, staleSources } from './freshness'

describe('dropStaleStragglers', () => {
  it('keeps only each source\'s rows from its own most recent pulled_at', () => {
    const rows = [
      { source: 'draftsharks', pulled_at: '2026-09-22T22:47:55Z', id: 'ds-new' },
      { source: 'draftsharks', pulled_at: '2026-09-21T12:13:19Z', id: 'ds-straggler' },
      { source: 'boone', pulled_at: '2026-09-20T17:46:37Z', id: 'boone-only' },
    ]
    const kept = dropStaleStragglers(rows)
    expect(kept.map(r => r.id).sort()).toEqual(['boone-only', 'ds-new'])
  })

  it('with a groupKey, judges staleness per group so a source publishing positions on different days keeps all of them', () => {
    // Boone publishes each position's trade-value article on a different day:
    // TE was pulled a day before QB/RB/WR, which made TE look like a straggler.
    const rows = [
      { source: 'boone', position: 'QB', pulled_at: '2026-11-19T21:28:12Z', id: 'qb' },
      { source: 'boone', position: 'TE', pulled_at: '2026-11-18T22:18:16Z', id: 'te' },
      { source: 'boone', position: 'TE', pulled_at: '2026-11-17T10:00:00Z', id: 'te-old' },
    ]
    expect(dropStaleStragglers(rows).map(r => r.id)).toEqual(['qb'])
    const kept = dropStaleStragglers(rows, r => `${r.source}|${r.position}`)
    expect(kept.map(r => r.id).sort()).toEqual(['qb', 'te'])
  })

  it('is a no-op when every source has a single pulled_at', () => {
    const rows = [
      { source: 'a', pulled_at: '2026-09-22T00:00:00Z', id: '1' },
      { source: 'b', pulled_at: '2026-09-22T00:00:00Z', id: '2' },
    ]
    expect(dropStaleStragglers(rows)).toEqual(rows)
  })
})

describe('onlyWeek', () => {
  const rows = [{ week: 2, id: 'a' }, { week: 3, id: 'b' }, { week: 3, id: 'c' }]

  it('filters to the given week', () => {
    expect(onlyWeek(rows, 3, r => r.week).map(r => r.id)).toEqual(['b', 'c'])
  })

  it('passes rows through unchanged when the week has not resolved yet', () => {
    expect(onlyWeek(rows, null, r => r.week)).toEqual(rows)
  })
})

describe('staleSources', () => {
  it('names sources present in `all` but missing from `current`', () => {
    const all = [{ source: 'boone' }, { source: 'cbs' }, { source: 'fantasypros' }]
    const current = [{ source: 'fantasypros' }]
    expect(staleSources(all, current)).toEqual(['boone', 'cbs'])
  })

  it('returns nothing when every source has current data', () => {
    const all = [{ source: 'a' }, { source: 'b' }]
    expect(staleSources(all, all)).toEqual([])
  })
})
