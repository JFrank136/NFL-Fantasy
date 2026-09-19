import { describe, it, expect } from 'vitest'
import { splitSnapshots, buildMovers, topMovers, type MoverRow } from './movers'
import type { RosSourceRow, BooneRosRow } from './blend'

const H = 60 * 60 * 1000

function pull(position: string, pulled_at: string, id: string) {
  return { position, pulled_at, id }
}

describe('splitSnapshots', () => {
  it('uses each position\'s newest pull as current and the newest pull at least minGap older as baseline', () => {
    const rows = [
      pull('WR', '2026-09-18T15:00:00Z', 'wr-now'),
      pull('WR', '2026-09-18T14:59:00Z', 'wr-rerun'),
      pull('WR', '2026-09-18T01:00:00Z', 'wr-prev'),
    ]
    const { current, baseline, baselineTimes } = splitSnapshots(rows, H)
    expect(current.map(r => r.id)).toEqual(['wr-now'])
    expect(baseline.map(r => r.id)).toEqual(['wr-prev'])
    expect(baselineTimes).toEqual(['2026-09-18T01:00:00Z'])
  })

  it('splits positions independently when they were pulled at different times', () => {
    const rows = [
      pull('RB', '2026-09-18T15:00:00Z', 'rb-now'),
      pull('RB', '2026-09-11T15:00:00Z', 'rb-old'),
      pull('WR', '2026-09-18T13:00:00Z', 'wr-now'),
      pull('WR', '2026-09-18T01:00:00Z', 'wr-prev'),
    ]
    const { current, baseline } = splitSnapshots(rows, H)
    expect(current.map(r => r.id).sort()).toEqual(['rb-now', 'wr-now'])
    expect(baseline.map(r => r.id).sort()).toEqual(['rb-old', 'wr-prev'])
  })

  it('returns no baseline when history does not reach back far enough', () => {
    const rows = [
      pull('RB', '2026-09-18T15:00:00Z', 'rb-now'),
      pull('RB', '2026-09-18T01:00:00Z', 'rb-prev'),
    ]
    const { baseline } = splitSnapshots(rows, 7 * 24 * H)
    expect(baseline).toEqual([])
  })
})

function ds(name: string, dsValue: number, ceiling = 10, position = 'RB'): RosSourceRow {
  return { canonicalName: name, playerName: name, position, team: null, dsValue, ceiling }
}
function boone(name: string, value: number, position = 'RB'): BooneRosRow {
  return { canonicalName: name, position, value }
}

describe('buildMovers', () => {
  it('computes change for the chosen metric against the baseline', () => {
    const current = { ds: [ds('a', 60), ds('b', 40)], boone: [] }
    const baseline = { ds: [ds('a', 50), ds('b', 45)], boone: null }
    const { rows, baselineAvailable } = buildMovers('ds', current, baseline)
    expect(baselineAvailable).toBe(true)
    const byName = Object.fromEntries(rows.map(r => [r.canonicalName, r]))
    expect(byName.a.change).toBe(10)
    expect(byName.b.change).toBe(-5)
    expect(byName.a.rank).toBe(1)
  })

  it('reports the baseline unavailable when a required source has none (blended needs both)', () => {
    const current = { ds: [ds('a', 60)], boone: [boone('a', 100)] }
    const baseline = { ds: [ds('a', 50)], boone: null }
    const blended = buildMovers('blended', current, baseline)
    expect(blended.baselineAvailable).toBe(false)
    expect(blended.rows[0].change).toBeNull()
    // ...but a DS-only metric is fine with just the DS baseline.
    expect(buildMovers('ds', current, baseline).baselineAvailable).toBe(true)
  })

  it('leaves change null for players with no baseline value', () => {
    const current = { ds: [ds('new', 60)], boone: [] }
    const baseline = { ds: [ds('old', 50)], boone: null }
    const { rows } = buildMovers('ds', current, baseline)
    expect(rows.find(r => r.canonicalName === 'new')!.change).toBeNull()
  })

  it('does not match same-name players across different positions', () => {
    const current = { ds: [ds('justin jefferson', 80, 10, 'WR')], boone: [] }
    const baseline = { ds: [ds('justin jefferson', 5, 1, 'LB')], boone: null }
    const { rows } = buildMovers('ds', current, baseline)
    expect(rows[0].change).toBeNull()
  })
})

describe('topMovers', () => {
  const row = (name: string, change: number | null): MoverRow => ({
    canonicalName: name, playerName: name, position: 'RB', team: null,
    current: 10, previous: 10, change, rank: 1,
  })

  it('splits into risers and fallers, sorted by magnitude, excluding unchanged and null', () => {
    const rows = [row('up1', 5), row('up2', 12), row('down1', -3), row('down2', -20), row('flat', 0), row('none', null)]
    const { risers, fallers } = topMovers(rows, 10)
    expect(risers.map(r => r.playerName)).toEqual(['up2', 'up1'])
    expect(fallers.map(r => r.playerName)).toEqual(['down2', 'down1'])
  })

  it('respects the limit', () => {
    const rows = [row('a', 1), row('b', 2), row('c', 3)]
    expect(topMovers(rows, 2).risers.map(r => r.playerName)).toEqual(['c', 'b'])
  })
})
