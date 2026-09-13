import type { BlendedRow, TrendDelta } from '../types'

export function computeDeltaByPlayer(curr: BlendedRow[], prev: BlendedRow[]): TrendDelta[] {
  const key = (r: BlendedRow) => (r.name + '|' + (r.pos||'') + '|' + (r.team||''))
  const prevMap = new Map(prev.map(r => [key(r), r]))
  return curr.map(r => {
    const o = prevMap.get(key(r))
    const d = (r.blended ?? null) != null && (o?.blended ?? null) != null
      ? Math.round((r.blended as number) - (o!.blended as number))
      : null
    return { playerId: key(r), name: r.name, pos: r.pos, team: r.team, delta: d }
  })
}
