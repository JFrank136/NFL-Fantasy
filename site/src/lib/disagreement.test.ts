import { describe, it, expect } from 'vitest'
import { currentDisagreements, directionDisagreements, RELEVANCE_RANK_CUTOFF } from './disagreement'
import type { BlendedRosRow } from './blend'
import type { MoverRow } from './movers'

function blended(name: string, ds: number | null, boone: number | null, booneScaled: number | null): BlendedRosRow {
  return {
    canonicalName: name, playerName: name, position: 'WR', team: null,
    dsValue: ds, booneValue: boone, booneScaled, ceiling: null, blendedValue: ds, overallRank: null,
  }
}

describe('currentDisagreements', () => {
  it('measures the gap on the DS scale and sorts by largest absolute gap', () => {
    const rows = [
      blended('small', 50, 100, 52),
      blended('bigBooneHigh', 40, 100, 60),
      blended('bigDsHigh', 80, 100, 55),
    ]
    const result = currentDisagreements(rows)
    expect(result.map(r => r.canonicalName)).toEqual(['bigDsHigh', 'bigBooneHigh', 'small'])
    expect(result[0].valueGap).toBe(-25)
    expect(result[1].valueGap).toBe(20)
  })

  it('ranks within each source independently', () => {
    const rows = [
      blended('a', 90, 10, 20),
      blended('b', 10, 90, 80),
    ]
    const byName = Object.fromEntries(currentDisagreements(rows).map(r => [r.canonicalName, r]))
    expect(byName.a.dsRank).toBe(1)
    expect(byName.a.booneRank).toBe(2)
    expect(byName.b.dsRank).toBe(2)
    expect(byName.b.booneRank).toBe(1)
  })

  it('skips deep-bench players ranked below the cutoff in both sources', () => {
    const rows = [blended('star', 90, 90, 40)]
    for (let i = 0; i < RELEVANCE_RANK_CUTOFF + 5; i++) rows.push(blended(`filler${i}`, 80 - i * 0.1, 80 - i * 0.1, 80 - i * 0.1))
    rows.push(blended('junk', -60, 1, 50)) // last in DS, last-ish in Boone, huge gap
    const names = currentDisagreements(rows).map(r => r.canonicalName)
    expect(names).toContain('star')
    expect(names).not.toContain('junk')
  })

  it('excludes players missing from either source', () => {
    const rows = [blended('dsOnly', 50, null, null), blended('booneOnly', null, 50, 50), blended('both', 50, 50, 50)]
    expect(currentDisagreements(rows).map(r => r.canonicalName)).toEqual(['both'])
  })
})

function mover(name: string, change: number | null): MoverRow {
  return { canonicalName: name, playerName: name, position: 'WR', team: null, current: 10, previous: 10, change, rank: 1 }
}

describe('directionDisagreements', () => {
  it('flags opposite moves and one-moves-one-flat, ignoring same direction and both flat', () => {
    const ds = [mover('opposite', 5), mover('oneFlat', 6), mover('same', 4), mover('bothFlat', 0.2), mover('bothDown', -3)]
    const boone = [mover('opposite', -4), mover('oneFlat', 0.5), mover('same', 8), mover('bothFlat', -0.3), mover('bothDown', -9)]
    const result = directionDisagreements(ds, boone)
    expect(result.map(r => r.canonicalName)).toEqual(['opposite', 'oneFlat'])
    expect(result[0].size).toBe(9)
  })

  it('skips players without a change in both sources', () => {
    expect(directionDisagreements([mover('a', null)], [mover('a', -5)])).toEqual([])
    expect(directionDisagreements([mover('a', 5)], [])).toEqual([])
  })
})
