// src/lib/freshness.ts
//
// Two distinct staleness failure modes show up across the site's Supabase
// "_latest" views and the raw-history "current pull" selection:
//
// 1. A "_latest" view (one row per player at THAT PLAYER'S OWN latest pull)
//    keeps serving a player's row from an older pull forever once a
//    source's newest pull stops including them -- e.g. ruled out/injured
//    and dropped from that week's rankings, but their last-ranked row
//    lingers with no signal it's stale. dropStaleStragglers fixes this by
//    keeping only rows at each source's own most recent pulled_at.
// 2. A whole source can simply not have run yet for the current week (e.g.
//    Boone's trade values still say "week 2" on a Tuesday that's now week
//    3) -- its rows are entirely real, just a week behind. onlyWeek filters
//    these out so an old week's values don't get silently blended in or
//    displayed as if they were current.

/** Keeps only each source's rows from its own most recent pulled_at. */
export function dropStaleStragglers<T extends { source: string; pulled_at: string }>(rows: T[]): T[] {
  const maxBySource = new Map<string, string>()
  rows.forEach(r => {
    const cur = maxBySource.get(r.source)
    if (!cur || r.pulled_at > cur) maxBySource.set(r.source, r.pulled_at)
  })
  return rows.filter(r => r.pulled_at === maxBySource.get(r.source))
}

/** Filters rows to the given week using a caller-supplied accessor (`week`
 * for weekly/trade-value rows, `as_of_week` for ROS rankings) -- a no-op
 * while the current week hasn't resolved yet. */
export function onlyWeek<T>(rows: T[], week: number | null, weekOf: (row: T) => number): T[] {
  if (week == null) return rows
  return rows.filter(r => weekOf(r) === week)
}

/** Source names present in `all` but missing from `current` -- e.g. every
 * source with a row for some week but none for the current one. Discovered
 * from the data itself rather than a hardcoded source list, so a new
 * source or one that starts/stops publishing weekly is picked up
 * automatically. */
export function staleSources<T extends { source: string }>(all: T[], current: T[]): string[] {
  const has = new Set(current.map(r => r.source))
  const stale = new Set<string>()
  all.forEach(r => { if (!has.has(r.source)) stale.add(r.source) })
  return Array.from(stale).sort()
}
