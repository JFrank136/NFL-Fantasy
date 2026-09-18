// src/lib/tradeValues.ts
//
// Pure calculation functions for the Trade Values page. No Supabase, no
// React -- the page fetches rows and hands them here. Pivots the long-format
// (one row per source per player) data into one row per player with each
// source as a column, plus a cross-source normalized score.

export interface TradeValueSourceRow {
  source: string
  playerName: string
  canonicalName: string
  team: string | null
  position: string
  valueCol1Label: string
  valueCol1: number | null
  valueCol2Label: string
  valueCol2: number | null
}

export type Scoring = 'ppr' | 'half-ppr'

const HALF_RE = /half/i
const FULL_RE = /(ppr|full)/i

function matchesScoring(label: string, scoring: Scoring): boolean {
  if (scoring === 'half-ppr') return HALF_RE.test(label)
  return FULL_RE.test(label) && !HALF_RE.test(label)
}

/**
 * Picks the right raw column for the requested scoring using the label text
 * itself rather than a hardcoded per-source table -- sources spell their
 * columns differently (Boone/CBS: HALF/PPR, USA Today: HALF/FULL, RSJ:
 * PPR-only, FantasyPros: blended VALUE, QB: 1QB/2QB) but every source that
 * actually splits by scoring format says so in its own label.
 *
 * A source that only publishes the OTHER scoring (RSJ: PPR only, no
 * half-PPR variant -- see src/sources/rsj_trade_values.py) returns null
 * rather than silently reusing its one value under the wrong label. A
 * source whose columns aren't scoring-specific at all (QB's 1QB/2QB
 * league-size split, FantasyPros' single blended VALUE) returns col1
 * regardless of the toggle -- there's nothing to switch between.
 */
export function valueForScoring(row: TradeValueSourceRow, scoring: Scoring): number | null {
  if (matchesScoring(row.valueCol1Label, scoring)) return row.valueCol1
  if (matchesScoring(row.valueCol2Label, scoring)) return row.valueCol2
  const other: Scoring = scoring === 'half-ppr' ? 'ppr' : 'half-ppr'
  if (matchesScoring(row.valueCol1Label, other)) return null
  return row.valueCol1
}

export interface PivotedTradeRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  valuesBySource: Record<string, number | null>
  normalizedScore: number | null
  rank: number | null
}

function percentileRank(value: number, sortedAsc: number[]): number {
  if (sortedAsc.length <= 1) return 100
  let countAtOrBelow = 0
  for (const v of sortedAsc) {
    if (v <= value) countAtOrBelow++
  }
  return ((countAtOrBelow - 1) / (sortedAsc.length - 1)) * 100
}

/**
 * Pivots long-format trade-value rows (one per source per player) into one
 * row per player, with each source's value for the requested scoring and a
 * normalizedScore averaging each source's percentile rank -- trade-value
 * charts use each source's own arbitrary scale (a few hundred to a few
 * thousand, position-agnostic so RB1 and WR1 are directly comparable), so
 * percentile rank puts every source on the same 0-100 footing before
 * averaging, rather than assuming the raw scales line up.
 *
 * `team` is filled from whichever source has one -- several sources don't
 * publish team on their trade-value page at all (always "" there), so a
 * player missing team from one source can still get it from another.
 */
export function pivotTradeValues(
  rows: TradeValueSourceRow[],
  scoring: Scoring,
): PivotedTradeRow[] {
  const bySource = new Map<string, number[]>()
  const valuesByPlayerSource = new Map<string, Map<string, number | null>>()
  const meta = new Map<string, { playerName: string; position: string; team: string | null }>()

  for (const row of rows) {
    const key = `${row.canonicalName}__${row.position}`
    const value = valueForScoring(row, scoring)

    if (!meta.has(key)) {
      meta.set(key, { playerName: row.playerName, position: row.position, team: row.team || null })
    } else if (row.team) {
      const existing = meta.get(key)!
      if (!existing.team) existing.team = row.team
    }

    if (!valuesByPlayerSource.has(key)) valuesByPlayerSource.set(key, new Map())
    valuesByPlayerSource.get(key)!.set(row.source, value)

    if (value != null) {
      if (!bySource.has(row.source)) bySource.set(row.source, [])
      bySource.get(row.source)!.push(value)
    }
  }

  const sortedBySource = new Map<string, number[]>()
  bySource.forEach((values, source) => sortedBySource.set(source, [...values].sort((a, b) => a - b)))

  const pivoted: PivotedTradeRow[] = Array.from(meta.entries()).map(([key, m]) => {
    const sourceValues = valuesByPlayerSource.get(key) ?? new Map()
    const valuesBySource: Record<string, number | null> = {}
    const percentiles: number[] = []
    sourceValues.forEach((value, source) => {
      valuesBySource[source] = value
      if (value != null) {
        const sorted = sortedBySource.get(source)
        if (sorted) percentiles.push(percentileRank(value, sorted))
      }
    })
    const normalizedScore = percentiles.length
      ? percentiles.reduce((sum, p) => sum + p, 0) / percentiles.length
      : null

    const [canonicalName] = [key.slice(0, key.lastIndexOf('__'))]
    return {
      canonicalName,
      playerName: m.playerName,
      position: m.position,
      team: m.team,
      valuesBySource,
      normalizedScore,
      rank: null,
    }
  })

  pivoted.sort((a, b) => {
    if (a.normalizedScore == null && b.normalizedScore == null) return 0
    if (a.normalizedScore == null) return 1
    if (b.normalizedScore == null) return -1
    return b.normalizedScore - a.normalizedScore
  })
  pivoted.forEach((row, i) => {
    row.rank = row.normalizedScore != null ? i + 1 : null
  })

  return pivoted
}

/** Sources that have at least one non-null value for the given scoring --
 * used to auto-hide a column (e.g. RSJ under half-PPR) instead of showing
 * an all-blank column. Discovered from the data itself, not a hardcoded
 * source list, so a new source or a source that starts/stops publishing a
 * scoring variant is picked up automatically. */
export function sourcesWithData(rows: PivotedTradeRow[]): string[] {
  const sources = new Set<string>()
  rows.forEach(r => {
    Object.entries(r.valuesBySource).forEach(([source, value]) => {
      if (value != null) sources.add(source)
    })
  })
  return Array.from(sources).sort()
}
