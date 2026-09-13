import type { BlendedRow, LeagueSettings } from '../types'

export function computeReplacementIndices(league: LeagueSettings) {
  const { teams, slots } = league
  return {
    QB: teams * slots.QB,
    RB: teams * slots.RB,
    WR: teams * slots.WR,
    TE: teams * slots.TE,
  }
}

export function computeVorp(rows: BlendedRow[], league: LeagueSettings) {
  const repIdx = computeReplacementIndices(league)
  const byPos: Record<string, BlendedRow[]> = { QB:[], RB:[], WR:[], TE:[] }
  for (const r of rows) {
    const pos = (r.pos||'').toUpperCase()
    if (!(pos in byPos)) continue
    byPos[pos].push(r)
  }
  const replacement: Record<string, number> = {}
  for (const pos of Object.keys(byPos)) {
    const list = byPos[pos].slice().sort((a,b)=>(b.blended??-1)-(a.blended??-1))
    const idx = Math.max(0, (repIdx as any)[pos]-1)
    const rep = list[idx]?.blended ?? 0
    replacement[pos] = rep
  }
  const withVorp = rows.map(r => {
    const pos = (r.pos||'').toUpperCase()
    const base = replacement[pos] ?? 0
    const v = (r.blended ?? 0) - base
    return { ...r, vorp: Math.round(v) }
  })
  return { replacement, rows: withVorp }
}
