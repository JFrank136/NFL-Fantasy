import type { PPR, SourceRow } from '../types'
import { tidyName } from './names'

// helper to read the first key that exists (case-insensitive)
const pick = (row: any, keys: string[]) => {
  const dict: Record<string, any> = {}
  for (const k of Object.keys(row)) dict[k.toLowerCase()] = row[k]
  for (const k of keys) {
    const v = dict[k.toLowerCase()]
    if (v !== undefined) return v
  }
  return undefined
}

export function mapBoone(row: any, ppr: PPR, week: number): SourceRow {
  // New: Position, half_ppr, full_ppr
  // Old: PosRank carries RB12; 0.5ppr / 1ppr; Unnamed: 2 (team, optional)
  const posRank = String(pick(row, ['PosRank']) ?? '').toUpperCase()
  const posFromRank = posRank.replace(/[^A-Z]/g, '') || undefined
  const posVal = pick(row, ['Position'])
  const pos = (posVal ? String(posVal).toUpperCase() : posFromRank) || undefined


  const team = pick(row, ['Team', 'Unnamed: 2']) // may be undefined (OK)

  const value = ppr === '0.5'
    ? Number(pick(row, ['half_ppr', '0.5ppr']))
    : Number(pick(row, ['full_ppr', '1ppr']))

  return {
    name: tidyName(String(pick(row, ['Name']) || '')),
    pos,
    team: team ? String(team).toUpperCase() : undefined,
    ppr,
    week,
    rawValue: Number.isFinite(value) ? value : null,
    source: 'boone'
  }
}

export function mapDraftSharks(row: any, ppr: PPR, week: number): SourceRow {
  // New: half_ppr, full_ppr
  // Old: 0.5ppr_value / 1ppr_value
  const value = ppr === '0.5'
    ? Number(pick(row, ['half_ppr', '0.5ppr_value']))
    : Number(pick(row, ['full_ppr', '1ppr_value']))

  const pos = String(pick(row, ['Pos', 'Position']) ?? '').toUpperCase() || undefined

  return {
    name: tidyName(String(pick(row, ['Name']) || '')),
    pos,
    team: undefined,
    ppr,
    week,
    rawValue: Number.isFinite(value) ? value : null,
    source: 'draftsharks'
  }
}

export function inferPprFromLeagueText(txt: string): PPR | null {
  const t = txt.toLowerCase()
  if (t.includes('0.5') && t.includes('ppr')) return '0.5'
  if (t.includes('half') && t.includes('ppr')) return '0.5'
  if (t.includes('full') && t.includes('ppr')) return '1.0'
  if (t.includes('1') && t.includes('ppr')) return '1.0'
  return null
}
