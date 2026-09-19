# Start/Sit and Add/Drop v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Start/Sit and Add/Drop v1 pages on the existing site, backed by pure, unit-tested calculation modules and the shared comparison components.

**Architecture:** Two pure lib modules (`startSit.ts`, `addDrop.ts`) sit on a shared `weeklyPool.ts` (weekly players + FLEX rank) and the existing `playerComparison.ts` (ROS pool, `highlightRow`). Two behavior-preserving hook extractions (`useWeeklyRows`, `useComparisonPool`) let the new pages reuse the fetch logic currently inlined in Rankings and PlayerComparison. Pages are thin: hooks -> pure functions -> `PlayerPicker` + `ComparisonTable`.

**Tech Stack:** React 18, TypeScript (strict), Vite, Vitest, Tailwind, Supabase JS client. Spec: `docs/superpowers/specs/2026-09-18-start-sit-and-add-drop-design.md`.

**Conventions for every task**
- `npm`/`npx` commands run from `in-season/site`; `git` commands run from the repo root `in-season/` (paths in every `git add` below are written relative to it, e.g. `site/src/...`). Run tests with `npx vitest run <file>`; full suite with `npm test`; type-check with `npx tsc -b`.
- Commit only the files named in the task. Never `git add -A`; the tree has unrelated modified `data/last_*.json` and README/DATA files that must stay out of feature commits.
- Every commit message ends with the line `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- `identityKey(name, position)` from `lib/blend.ts` yields `"<canonicalName>::<position>"` and is the join key everywhere.

## File map

| File | Action | Responsibility |
|---|---|---|
| `src/lib/weeklyPool.ts` | create | `WeeklyPlayer`, `buildWeeklyPool`, `computeFlexRanks`, `formatOpponent`, position constants |
| `src/lib/weeklyPool.test.ts` | create | tests for the above |
| `src/lib/useWeeklyRows.ts` | create | `useCurrentWeek` + `useWeeklyRows(scoring)` (moved out of Rankings) |
| `src/pages/Rankings.tsx` | modify | consume `useWeeklyRows` instead of inline hooks |
| `src/lib/useComparisonPool.ts` | create | ROS pool hook (moved out of PlayerComparison) |
| `src/lib/playerComparison.ts` | modify | export `round1`, add `formatCell` |
| `src/lib/playerComparison.test.ts` | modify | `formatCell` tests |
| `src/pages/PlayerComparison.tsx` | modify | consume `useComparisonPool` + shared `formatCell` |
| `src/lib/startSit.ts` | create | rows, recommendation, confidence, reasons |
| `src/lib/startSit.test.ts` | create | tests |
| `src/lib/addDrop.ts` | create | rows + two-step analysis |
| `src/lib/addDrop.test.ts` | create | tests |
| `src/pages/StartSit.tsx` | create | Start/Sit page |
| `src/pages/AddDrop.tsx` | create | Add/Drop page |
| `src/nav.ts`, `src/pages/index.ts`, `src/App.tsx` | modify | wiring |
| `../SITE_ROADMAP.md`, `README.md` | modify | tick roadmap items, document pages |

---

### Task 1: Weekly pool with FLEX rank

**Files:**
- Create: `src/lib/weeklyPool.ts`
- Test: `src/lib/weeklyPool.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/lib/weeklyPool.test.ts`:

```ts
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
    const ranks = computeFlexRanks([row('te', 'TE', 9), row('rb', 'RB', 4), row('wr', 'WR', 2)])
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
    ])
    expect(ranks.has('qb::QB')).toBe(false)
    expect(ranks.has('bye::RB')).toBe(false)
    expect(ranks.has('none::WR')).toBe(false)
    expect(ranks.get('rb::RB')).toBe(1)
  })

  it('gives tied scores the same rank', () => {
    const ranks = computeFlexRanks([row('a', 'RB', 5), row('b', 'WR', 5), row('c', 'TE', 6)])
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
    ])
    expect(pool.map(p => p.canonicalName).sort()).toEqual(['bye', 'qb', 'rb'])
    const rb = pool.find(p => p.canonicalName === 'rb')!
    expect(rb).toMatchObject({ key: 'rb::RB', flexRank: 1, positionRank: 2, dsRank: 7, booneRank: 5, smytheRank: 6, isBye: false })
    expect(pool.find(p => p.canonicalName === 'bye')).toMatchObject({ isBye: true, flexRank: null })
    expect(pool.find(p => p.canonicalName === 'qb')!.flexRank).toBeNull()
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
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/weeklyPool.test.ts`
Expected: FAIL (cannot resolve `./weeklyPool`).

- [ ] **Step 3: Write minimal implementation**

Create `src/lib/weeklyPool.ts`:

```ts
// src/lib/weeklyPool.ts
//
// Shared weekly player shape for Start/Sit and Add/Drop. Pure: no React, no
// Supabase. Built from Rankings' AggregatedWeeklyRow output.
//
// FLEX rank: aggregateWeeklyRanks re-ranks within each position, so "RB4 vs
// RB6" hides how far apart they are overall. Before that re-rank, the
// weighted score is on a shared scale for RB/WR/TE (Boone/Smyth are pulled
// from Yahoo's FLX query; Draft Sharks ranks overall), so ranking every
// RB/WR/TE by that score gives a cross-position rank. QBs are ranked against
// QBs only, so they get none.

import { identityKey, type AggregatedWeeklyRow } from './blend'

export const WEEKLY_POSITIONS = ['QB', 'RB', 'WR', 'TE']
export const FLEX_POSITIONS = ['RB', 'WR', 'TE']

export interface WeeklyPlayer {
  key: string
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  /** Raw opponent string as stored, e.g. "@KC". Null/empty = bye week. */
  opponent: string | null
  isBye: boolean
  /** Weighted average of source ranks (lower = better). The recommendation anchor. */
  aggregateScore: number | null
  positionRank: number | null
  flexRank: number | null
  dsRank: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
}

/**
 * FLEX rank by identity key. Only scored, non-bye RB/WR/TE rows are ranked;
 * ties share a rank (competition ranking: 1, 1, 3).
 */
export function computeFlexRanks(rows: AggregatedWeeklyRow[]): Map<string, number> {
  const eligible = rows.filter(
    r => FLEX_POSITIONS.includes(r.position) && r.aggregateScore != null && !!r.opponent,
  )
  const scores = eligible.map(r => r.aggregateScore as number)
  const ranks = new Map<string, number>()
  eligible.forEach(r => {
    const better = scores.filter(s => s < (r.aggregateScore as number)).length
    ranks.set(identityKey(r.canonicalName, r.position), better + 1)
  })
  return ranks
}

export function buildWeeklyPool(rows: AggregatedWeeklyRow[]): WeeklyPlayer[] {
  const flex = computeFlexRanks(rows)
  return rows
    .filter(r => WEEKLY_POSITIONS.includes(r.position))
    .map(r => {
      const key = identityKey(r.canonicalName, r.position)
      return {
        key,
        canonicalName: r.canonicalName,
        playerName: r.playerName,
        position: r.position,
        team: r.team,
        opponent: r.opponent,
        isBye: !r.opponent,
        aggregateScore: r.aggregateScore,
        positionRank: r.aggregateRank,
        flexRank: flex.get(key) ?? null,
        dsRank: r.draftsharksRank,
        booneRank: r.booneRank,
        smytheRank: r.smytheRank,
        dsProjection: r.dsProjection,
        dsFloor: r.dsFloor,
        dsCeiling: r.dsCeiling,
      }
    })
}

/** "@KC" stays, "at IND" -> "@IND", "NO" -> "vs NO", empty -> "BYE". */
export function formatOpponent(opponent: string | null): string {
  if (!opponent) return 'BYE'
  if (opponent.startsWith('@')) return opponent
  const at = opponent.match(/^at\s+(.+)$/i)
  if (at) return `@${at[1]}`
  return `vs ${opponent}`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/weeklyPool.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add site/src/lib/weeklyPool.ts site/src/lib/weeklyPool.test.ts
git commit -m "Add weekly player pool with cross-position FLEX rank

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Extract `useWeeklyRows` from Rankings

Behavior-preserving move. Rankings' weekly tab must look and behave identically afterwards.

**Files:**
- Create: `src/lib/useWeeklyRows.ts`
- Modify: `src/pages/Rankings.tsx` (remove `useCurrentWeek` at ~lines 124-149 and `useWeeklyTab` at ~lines 179-251; edit the component at ~lines 258-264 and the imports at lines 1-6)

- [ ] **Step 1: Create the hook**

Create `src/lib/useWeeklyRows.ts` (this is the existing logic moved verbatim, with the week fetch folded in):

```ts
// src/lib/useWeeklyRows.ts
//
// Shared "current week's aggregated weekly rankings" fetch. Extracted from
// Rankings' weekly tab so Start/Sit and Add/Drop reuse the exact same fetch,
// grouping and aggregation instead of re-deriving it per page.

import { useEffect, useState } from 'react'
import { supabase, fetchAllRows, type RankingLatestRow } from './supabase'
import { aggregateWeeklyRanks, identityKey, normalizePosition, type AggregatedWeeklyRow } from './blend'
import type { Scoring } from './useBlendedRos'

export function useCurrentWeek() {
  const [week, setWeek] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    supabase
      .from('in_season_rankings_latest')
      .select('week')
      .in('source', ['boone', 'smythe'])
      .order('week', { ascending: false })
      .limit(1)
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) {
          console.error('Failed to fetch current week:', error)
          setError(error.message)
          return
        }
        setWeek(data?.[0]?.week ?? null)
      })
    return () => { cancelled = true }
  }, [])

  return { week, error }
}

export interface WeeklyRowsResult {
  rows: AggregatedWeeklyRow[]
  week: number | null
  loading: boolean
  error: string | null
  freshest: string | null
}

export function useWeeklyRows(scoring: Scoring): WeeklyRowsResult {
  const { week, error: weekError } = useCurrentWeek()
  const [rows, setRows] = useState<AggregatedWeeklyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    if (week == null) {
      if (weekError) {
        setError(weekError)
        setLoading(false)
      }
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    // One week across all sources is ~1400 rows (DS alone includes DL/K/DST),
    // over PostgREST's 1000-row cap -- paginate or later players (e.g. a QB's
    // DS row) silently drop out.
    fetchAllRows<RankingLatestRow>((from, to) =>
      supabase
        .from('in_season_rankings_latest')
        .select('*')
        .eq('scoring', scoring)
        .eq('week', week)
        .order('id')
        .range(from, to),
    )
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) { setError(error.message); setLoading(false); return }

        const rankingRows = data
        const byPlayer = new Map<string, RankingLatestRow[]>()
        rankingRows.forEach(r => {
          const key = identityKey(r.canonical_name, r.position)
          const list = byPlayer.get(key) ?? []
          list.push(r)
          byPlayer.set(key, list)
        })

        const players = Array.from(byPlayer.values()).map(sourceRows => {
          const ds = sourceRows.find(r => r.source === 'draftsharks')
          const boone = sourceRows.find(r => r.source === 'boone')
          const smythe = sourceRows.find(r => r.source === 'smythe')
          const any = ds ?? boone ?? smythe ?? sourceRows[0]
          return {
            canonicalName: any.canonical_name,
            playerName: any.player_name,
            position: normalizePosition(any.position),
            team: any.team,
            draftsharksRank: ds?.rank ?? null,
            booneRank: boone?.rank ?? null,
            smytheRank: smythe?.rank ?? null,
            dsProjection: ds?.projection ?? null,
            dsFloor: ds?.floor_proj ?? null,
            dsCeiling: ds?.ceiling_proj ?? null,
            opponent: any.opponent,
          }
        })

        setRows(aggregateWeeklyRanks(players))
        setFreshest(rankingRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), rankingRows[0]?.pulled_at ?? '') || null)
        setLoading(false)
      })

    return () => { cancelled = true }
  }, [scoring, week, weekError])

  return { rows, week, loading, error, freshest }
}
```

Before saving, diff the body against the current `useWeeklyTab` in `Rankings.tsx` (lines ~179-251) and confirm nothing was dropped.

- [ ] **Step 2: Switch Rankings to the hook**

In `src/pages/Rankings.tsx`:
1. Delete the `useCurrentWeek` function and the `useWeeklyTab` function.
2. Add `import { useWeeklyRows } from '../lib/useWeeklyRows'` next to the other `../lib` imports.
3. In `Rankings()`, replace

```tsx
  const { week, error: weekError } = useCurrentWeek()
```
and
```tsx
  const weekly = useWeeklyTab(scoring, week, weekError)
```
with the single line (place it where the second line was):
```tsx
  const weekly = useWeeklyRows(scoring)
  const week = weekly.week
```
4. Remove imports no longer used in the file. After the move, check each of `fetchAllRows`, `RankingLatestRow`, `aggregateWeeklyRanks`, `identityKey`, `normalizePosition`, `supabase` with Grep; delete any that have zero remaining uses (`identityKey` is still used by `useRosTab`; `AggregatedWeeklyRow` is still used by `WEEKLY_COLUMNS`). `noUnusedLocals` is off, so tsc will not flag leftovers -- check by hand.

- [ ] **Step 3: Type-check and run the full suite**

Run: `npx tsc -b && npm test`
Expected: no type errors; all existing tests pass.

- [ ] **Step 4: Verify Rankings' Weekly tab unchanged in the browser**

Use `preview_start` with name `site` (from `.claude/launch.json`), open the Rankings page, Weekly tab. Confirm: the "Week N" badge shows a number, QB rows load with Agg. Rank / DS Rank / Boone Rank / Floor / DS Proj / Ceiling populated, switching QB/RB/WR/TE works, PPR/Half-PPR toggle reloads, and `read_console_messages` shows no errors.

- [ ] **Step 5: Commit**

```bash
git add site/src/lib/useWeeklyRows.ts site/src/pages/Rankings.tsx
git commit -m "Extract useWeeklyRows from Rankings for reuse by Start/Sit and Add/Drop

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Extract `useComparisonPool` and shared `formatCell`

**Files:**
- Modify: `src/lib/playerComparison.ts` (export `round1`, add `formatCell`)
- Modify: `src/lib/playerComparison.test.ts` (add `formatCell` tests)
- Create: `src/lib/useComparisonPool.ts`
- Modify: `src/pages/PlayerComparison.tsx`

- [ ] **Step 1: Write the failing `formatCell` test**

In `src/lib/playerComparison.test.ts`, change the import line
```ts
import { buildComparisonPool, comparisonRows, highlightRow, summarizeComparison, type ComparisonPlayer } from './playerComparison'
```
to
```ts
import { buildComparisonPool, comparisonRows, formatCell, highlightRow, summarizeComparison, type ComparisonPlayer } from './playerComparison'
```
and append at the end of the file:

```ts
describe('formatCell', () => {
  it('formats each cell kind and shows a dash for null', () => {
    expect(formatCell(null, 'value')).toBe('—')
    expect(formatCell(12.34, 'value')).toBe('12.3')
    expect(formatCell(4, 'rank')).toBe('#4')
    expect(formatCell(3.46, 'signed')).toBe('+3.5')
    expect(formatCell(-2, 'signed')).toBe('-2')
    expect(formatCell('-1.6%', 'text')).toBe('-1.6%')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/lib/playerComparison.test.ts`
Expected: FAIL (`formatCell` is not exported).

- [ ] **Step 3: Implement `formatCell` and export `round1`**

In `src/lib/playerComparison.ts`, change `const round1 = (n: number) => Math.round(n * 10) / 10` to `export const round1 = (n: number) => Math.round(n * 10) / 10`, and add directly below it:

```ts
/** Display text for one comparison cell (shared by Player Comparison, Start/Sit, Add/Drop). */
export function formatCell(value: number | string | null, format: CellFormat): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  switch (format) {
    case 'rank': return `#${value}`
    case 'signed': return `${value > 0 ? '+' : ''}${round1(value)}`
    default: return String(round1(value))
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/lib/playerComparison.test.ts`
Expected: PASS.

- [ ] **Step 5: Create the pool hook**

Create `src/lib/useComparisonPool.ts` (the existing `useMemo` from `PlayerComparison.tsx`, moved verbatim):

```ts
// src/lib/useComparisonPool.ts
//
// Shared "selectable ROS players" pool: blended ROS value, ceiling, trend
// and SOS per player. Extracted from Player Comparison so Add/Drop and
// Start/Sit reuse the exact same pool.

import { useMemo } from 'react'
import { useRosHistory } from './useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from './useBlendedRos'
import { blendRosValues, identityKey } from './blend'
import { buildMovers, splitSnapshots, TIMEFRAME_MIN_GAP_MS } from './movers'
import { buildComparisonPool, type ComparisonPlayer } from './playerComparison'

export interface ComparisonPoolResult {
  pool: ComparisonPlayer[]
  freshest: string
  loading: boolean
  error: string | null
}

export function useComparisonPool(scoring: Scoring): ComparisonPoolResult {
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)

  const { pool, freshest } = useMemo(() => {
    const gap = TIMEFRAME_MIN_GAP_MS.latest
    const ds = splitSnapshots(dsRows, gap)
    const boone = splitSnapshots(booneRows, gap)
    const current = { ds: ds.current.map(toDsRosInput), boone: boone.current.map(r => toBooneRosInput(r, scoring)) }

    const { rows: movers } = buildMovers('blended', current, {
      ds: ds.baseline.length ? ds.baseline.map(toDsRosInput) : null,
      boone: boone.baseline.length ? boone.baseline.map(r => toBooneRosInput(r, scoring)) : null,
    })
    const trendByKey = new Map(movers.map(m => [identityKey(m.canonicalName, m.position), m.change]))
    const sosByKey = new Map(ds.current.map(r => [identityKey(r.canonical_name, r.position), r.strength_of_schedule]))

    return {
      pool: buildComparisonPool(blendRosValues(current.ds, current.boone), trendByKey, sosByKey),
      freshest: ds.current.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
    }
  }, [dsRows, booneRows, scoring])

  return { pool, freshest, loading, error }
}
```

- [ ] **Step 6: Switch PlayerComparison to the hook and shared `formatCell`**

In `src/pages/PlayerComparison.tsx`:
1. Delete the local `r1` and `formatCell` definitions (lines ~17-27).
2. Replace the block from `const { dsRows, booneRows, loading, error } = useRosHistory(scoring)` through the end of the `const { pool, freshest } = useMemo(...)` (lines ~32-51) with:
```tsx
  const { pool, freshest, loading, error } = useComparisonPool(scoring)
```
3. Fix the imports at the top to exactly:
```tsx
import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useComparisonPool } from '../lib/useComparisonPool'
import type { Scoring } from '../lib/useBlendedRos'
import {
  comparisonRows, formatCell, summarizeComparison,
  type ComparisonPlayer,
} from '../lib/playerComparison'
```
(`buildComparisonPool`, `CellFormat`, `blend`, `movers` and `useRosHistory` are no longer used here.)

- [ ] **Step 7: Type-check, test, and spot-check the page**

Run: `npx tsc -b && npm test`
Expected: no errors, all tests pass. Then in the browser (`preview_start` name `site`), open Player Comparison, add two players and confirm the table and summary render as before with no console errors.

- [ ] **Step 8: Commit**

```bash
git add site/src/lib/playerComparison.ts site/src/lib/playerComparison.test.ts site/src/lib/useComparisonPool.ts site/src/pages/PlayerComparison.tsx
git commit -m "Extract useComparisonPool and shared formatCell from Player Comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Start/Sit calculation module

**Files:**
- Create: `src/lib/startSit.ts`
- Test: `src/lib/startSit.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/lib/startSit.test.ts`:

```ts
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

  it('highlights position rank only when everyone shares a position; ROS is context only', () => {
    const mixed = startSitRows([wp('rb'), wp('wr', { position: 'WR', key: 'wr::WR', positionRank: 1 })], new Map())
    expect(mixed.find(r => r.id === 'positionRank')!.highlights).toEqual([null, null])
    const ros = startSitRows([wp('a'), wp('b')], new Map([['a::RB', 80], ['b::RB', 40]]))
    const rosRow = ros.find(r => r.id === 'ros')!
    expect(rosRow.values).toEqual([80, 40])
    expect(rosRow.highlights).toEqual([null, null])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/lib/startSit.test.ts`
Expected: FAIL (cannot resolve `./startSit`).

- [ ] **Step 3: Write the implementation**

Create `src/lib/startSit.ts`:

```ts
// src/lib/startSit.ts
//
// Pure calculations for the Start/Sit page: row-based comparison and the
// recommendation. No React, no Supabase.
//
// Anchor: the weighted weekly rank score (lower = better). It is on a shared
// scale for RB/WR/TE (FLEX) and separately for QBs, so a QB vs non-QB
// comparison gets no recommendation. See
// docs/superpowers/specs/2026-09-18-start-sit-and-add-drop-design.md.

import { highlightRow, round1, type CellFormat, type ComparisonRow, type Highlight } from './playerComparison'
import { FLEX_POSITIONS, formatOpponent, type WeeklyPlayer } from './weeklyPool'

/** Score-gap cutoffs (in weighted-rank points). Retune after a season of data. */
export const CONFIDENCE_THRESHOLDS = { high: 5, medium: 2 }
/** Smallest FLEX-rank gap worth calling out as a reason. */
export const FLEX_GAP_NOTE_MIN = 5
/** Smallest ceiling / projection edge worth calling out as a reason (points). */
export const CEILING_NOTE_MIN = 2
export const PROJECTION_NOTE_MIN = 1

export type Confidence = 'High' | 'Medium' | 'Toss-up'

export interface StartSitRecommendation {
  status: 'ok' | 'not-comparable' | 'insufficient'
  starterKey: string | null
  confidence: Confidence | null
  reasons: string[]
  note: string | null
}

interface RowSpec {
  id: string
  label: string
  format: CellFormat
  /** null = show but never highlight. */
  better: 'higher' | 'lower' | null
  pick: (p: WeeklyPlayer, rosByKey: Map<string, number | null>) => number | string | null
}

const ROW_SPECS: RowSpec[] = [
  { id: 'score', label: 'Rank score (lower = better)', format: 'value', better: 'lower', pick: p => p.aggregateScore },
  { id: 'positionRank', label: 'Position rank', format: 'rank', better: 'lower', pick: p => p.positionRank },
  { id: 'flexRank', label: 'FLEX rank (RB/WR/TE)', format: 'rank', better: 'lower', pick: p => p.flexRank },
  { id: 'dsRank', label: 'Draft Sharks rank', format: 'rank', better: 'lower', pick: p => p.dsRank },
  { id: 'booneRank', label: 'Boone rank', format: 'rank', better: 'lower', pick: p => p.booneRank },
  { id: 'smytheRank', label: 'Smyth rank', format: 'rank', better: 'lower', pick: p => p.smytheRank },
  { id: 'dsProjection', label: 'DS projection', format: 'value', better: 'higher', pick: p => p.dsProjection },
  { id: 'dsFloor', label: 'DS floor', format: 'value', better: 'higher', pick: p => p.dsFloor },
  { id: 'dsCeiling', label: 'DS ceiling', format: 'value', better: 'higher', pick: p => p.dsCeiling },
  // Display only: no matchup-rating source exists yet.
  { id: 'opponent', label: 'Opponent', format: 'text', better: null, pick: p => formatOpponent(p.opponent) },
  // Context only, never used in the recommendation.
  { id: 'ros', label: 'ROS value (context)', format: 'value', better: null, pick: (p, ros) => ros.get(p.key) ?? null },
]

/** Row-based comparison (one row per stat, one column per player). */
export function startSitRows(players: WeeklyPlayer[], rosByKey: Map<string, number | null>): ComparisonRow[] {
  const samePosition = new Set(players.map(p => p.position)).size <= 1
  return ROW_SPECS.map(spec => {
    const values = players.map(p => spec.pick(p, rosByKey))
    const canHighlight = spec.better != null && spec.format !== 'text' && (spec.id !== 'positionRank' || samePosition)
    let highlights: Highlight[] = values.map(() => null)
    if (canHighlight) {
      // A bye-week player's numbers shouldn't decide who is best/worst.
      const forHighlight = values.map((v, i) => (players[i].isBye ? null : v)) as (number | null)[]
      highlights = highlightRow(forHighlight, spec.better as 'higher' | 'lower')
    }
    return { id: spec.id, label: spec.label, format: spec.format, values, highlights }
  })
}

/** RB/WR/TE share one scale ("FLEX"); every other position is its own group. */
const scaleGroup = (p: WeeklyPlayer) => (FLEX_POSITIONS.includes(p.position) ? 'FLEX' : p.position)

function confidenceFor(gap: number): Confidence {
  if (gap >= CONFIDENCE_THRESHOLDS.high) return 'High'
  if (gap >= CONFIDENCE_THRESHOLDS.medium) return 'Medium'
  return 'Toss-up'
}

function buildReasons(top: WeeklyPlayer, next: WeeklyPlayer): string[] {
  const reasons: string[] = []

  if (top.dsRank != null && next.dsRank != null && top.booneRank != null && next.booneRank != null) {
    const dsSign = Math.sign(next.dsRank - top.dsRank) // > 0: Draft Sharks favors the starter
    const booneSign = Math.sign(next.booneRank - top.booneRank)
    const favored = (s: number) => (s > 0 ? top : next)
    if (dsSign > 0 && booneSign > 0) {
      reasons.push(`Ranked ahead of ${next.playerName} by both Draft Sharks and Boone.`)
    } else if (dsSign * booneSign < 0) {
      reasons.push(`Sources split: Draft Sharks favors ${favored(dsSign).playerName}, Boone favors ${favored(booneSign).playerName}.`)
    }
  }

  if (top.flexRank != null && next.flexRank != null && next.flexRank - top.flexRank >= FLEX_GAP_NOTE_MIN) {
    reasons.push(`FLEX rank #${top.flexRank} vs #${next.flexRank} for ${next.playerName}.`)
  }

  if (top.dsCeiling != null && next.dsCeiling != null && next.dsCeiling - top.dsCeiling >= CEILING_NOTE_MIN) {
    reasons.push(`${next.playerName} has the higher ceiling (${round1(next.dsCeiling)} vs ${round1(top.dsCeiling)}).`)
  } else if (top.dsProjection != null && next.dsProjection != null && top.dsProjection - next.dsProjection >= PROJECTION_NOTE_MIN) {
    reasons.push(`Projected ${round1(top.dsProjection)} pts vs ${round1(next.dsProjection)}.`)
  }

  if (reasons.length === 0) {
    reasons.push(`Rank score ${round1(top.aggregateScore as number)} vs ${round1(next.aggregateScore as number)}.`)
  }
  return reasons.slice(0, 2)
}

export function recommendStartSit(players: WeeklyPlayer[]): StartSitRecommendation {
  const byes = players.filter(p => p.isBye)
  const byeNote = byes.length
    ? `${byes.map(p => p.playerName).join(', ')} ${byes.length === 1 ? 'is' : 'are'} on a bye and excluded.`
    : null
  const valid = players.filter(p => !p.isBye && p.aggregateScore != null)

  if (valid.length < 2) {
    return {
      status: 'insufficient', starterKey: null, confidence: null, reasons: [],
      note: [byeNote, 'Add at least two players who are playing this week and have a ranking.'].filter(Boolean).join(' '),
    }
  }

  if (new Set(valid.map(scaleGroup)).size > 1) {
    return {
      status: 'not-comparable', starterKey: null, confidence: null, reasons: [],
      note: [
        byeNote,
        "QBs are ranked against QBs only, so a QB can't be compared with an RB, WR or TE. Compare like with like.",
      ].filter(Boolean).join(' '),
    }
  }

  const sorted = [...valid].sort((a, b) => (a.aggregateScore as number) - (b.aggregateScore as number))
  const top = sorted[0]
  const next = sorted[1]
  const gap = (next.aggregateScore as number) - (top.aggregateScore as number)

  return {
    status: 'ok',
    starterKey: top.key,
    confidence: confidenceFor(gap),
    reasons: buildReasons(top, next),
    note: byeNote,
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/lib/startSit.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add site/src/lib/startSit.ts site/src/lib/startSit.test.ts
git commit -m "Add Start/Sit calculation module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Add/Drop calculation module

**Files:**
- Create: `src/lib/addDrop.ts`
- Test: `src/lib/addDrop.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/lib/addDrop.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { analyzeAddDrop, addDropRows, ADD_DROP_THRESHOLDS } from './addDrop'
import type { ComparisonPlayer } from './playerComparison'
import type { WeeklyPlayer } from './weeklyPool'

function cp(name: string, overrides: Partial<ComparisonPlayer> = {}): ComparisonPlayer {
  return {
    key: `${name}::WR`, canonicalName: name, playerName: name, position: 'WR', team: 'XXX',
    blended: 50, ds: 50, boone: 50, ceiling: 20, overallRank: 10, positionRank: 5,
    trend: 0, sos: null, disagreement: null, ...overrides,
  }
}

function wp(key: string, overrides: Partial<WeeklyPlayer> = {}): WeeklyPlayer {
  return {
    key, canonicalName: key, playerName: key, position: 'WR', team: 'XXX', opponent: '@BUF', isBye: false,
    aggregateScore: 10, positionRank: 5, flexRank: 12, dsRank: 10, booneRank: 10, smytheRank: 10,
    dsProjection: 10, dsFloor: 5, dsCeiling: 18, ...overrides,
  }
}

describe('analyzeAddDrop', () => {
  it('needs at least one valued add and one valued drop', () => {
    expect(analyzeAddDrop([], [cp('d')]).status).toBe('insufficient')
    expect(analyzeAddDrop([cp('a')], []).status).toBe('insufficient')
    expect(analyzeAddDrop([cp('a', { blended: null })], [cp('d')]).status).toBe('insufficient')
  })

  it('compares the best add against the weakest drop', () => {
    const r = analyzeAddDrop(
      [cp('a1', { blended: 40 }), cp('a2', { blended: 60 })],
      [cp('d1', { blended: 30 }), cp('d2', { blended: 45 })],
    )
    expect(r.bestAdd?.canonicalName).toBe('a2')
    expect(r.dropTarget?.canonicalName).toBe('d1')
    expect(r.gap).toBe(30)
  })

  it('maps the gap to Yes / Marginal / No at the configured thresholds', () => {
    const verdict = (gap: number) => analyzeAddDrop([cp('a', { blended: 30 + gap })], [cp('d', { blended: 30 })]).verdict
    expect(verdict(ADD_DROP_THRESHOLDS.yes)).toBe('Yes')
    expect(verdict(ADD_DROP_THRESHOLDS.yes - 0.1)).toBe('Marginal')
    expect(verdict(ADD_DROP_THRESHOLDS.marginal)).toBe('Marginal')
    expect(verdict(ADD_DROP_THRESHOLDS.marginal - 0.1)).toBe('No')
    expect(verdict(-10)).toBe('No')
  })

  it('adds an upside note when an add clearly out-ceilings the drop, even on a No', () => {
    const r = analyzeAddDrop(
      [cp('boom', { blended: 28, ceiling: 40 })],
      [cp('safe', { blended: 30, ceiling: 20 })],
    )
    expect(r.verdict).toBe('No')
    expect(r.upsideNote).toContain('boom has the higher ceiling than safe (40 vs 20)')
  })

  it('has no upside note without a clear ceiling edge or with missing ceilings', () => {
    expect(analyzeAddDrop([cp('a', { ceiling: 20.5 })], [cp('d', { ceiling: 20 })]).upsideNote).toBeNull()
    expect(analyzeAddDrop([cp('a', { ceiling: null })], [cp('d', { ceiling: 20 })]).upsideNote).toBeNull()
  })

  it('caveats a drop suggestion whose ceiling beats the add', () => {
    const r = analyzeAddDrop(
      [cp('a', { blended: 60, ceiling: 20 })],
      [cp('lottery', { blended: 30, ceiling: 45 })],
    )
    expect(r.dropCaveat).toContain('lottery')
    expect(r.dropCaveat).toContain('higher ceiling than a')
  })

  it('has no caveat when the drop target has no ceiling edge', () => {
    expect(analyzeAddDrop([cp('a', { ceiling: 30 })], [cp('d', { ceiling: 20 })]).dropCaveat).toBeNull()
  })
})

describe('addDropRows', () => {
  it('highlights ROS value, ceiling and trend across all columns, add or drop', () => {
    const rows = addDropRows(
      [cp('a', { blended: 70, ceiling: 30, trend: 2 }), cp('d', { blended: 40, ceiling: 25, trend: -1 })],
      new Map(),
    )
    expect(rows.find(r => r.id === 'blended')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'ceiling')!.highlights).toEqual(['best', 'worst'])
    expect(rows.find(r => r.id === 'trend')!.highlights).toEqual(['best', 'worst'])
  })

  it('joins this-week outlook by key and shows a dash when there is none', () => {
    const rows = addDropRows(
      [cp('a'), cp('b')],
      new Map([['a::WR', wp('a::WR', { dsProjection: 14, flexRank: 8, positionRank: 3 })]]),
    )
    expect(rows.find(r => r.id === 'weekProjection')!.values).toEqual([14, null])
    expect(rows.find(r => r.id === 'weekFlexRank')!.values).toEqual([8, null])
    expect(rows.find(r => r.id === 'weekPositionRank')!.values).toEqual([3, null])
  })

  it('highlights weekly position rank only when every player shares a position', () => {
    const map = new Map([
      ['a::WR', wp('a::WR', { positionRank: 3 })],
      ['b::RB', wp('b::RB', { position: 'RB', positionRank: 9 })],
    ])
    const mixed = addDropRows([cp('a'), cp('b', { key: 'b::RB', position: 'RB' })], map)
    expect(mixed.find(r => r.id === 'weekPositionRank')!.highlights).toEqual([null, null])
  })

  it('shows SOS as text with no highlight', () => {
    const rows = addDropRows([cp('a', { sos: '-1.6%' }), cp('b', { sos: '+2.0%' })], new Map())
    const sos = rows.find(r => r.id === 'sos')!
    expect(sos.values).toEqual(['-1.6%', '+2.0%'])
    expect(sos.highlights).toEqual([null, null])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/lib/addDrop.test.ts`
Expected: FAIL (cannot resolve `./addDrop`).

- [ ] **Step 3: Write the implementation**

Create `src/lib/addDrop.ts`:

```ts
// src/lib/addDrop.ts
//
// Pure calculations for the Add/Drop page. No React, no Supabase.
//
// Two-step problem: (1) is anyone worth adding? (2) if so, who to drop?
// ROS value ("who is better right now") and DS ceiling ("who has the better
// best case") stay separate axes -- no combined score in v1, and no
// cross-position logic.

import { highlightRow, round1, type CellFormat, type ComparisonPlayer, type ComparisonRow } from './playerComparison'
import type { WeeklyPlayer } from './weeklyPool'

/** Blended-ROS-value gap (best add minus weakest drop) cutoffs. Tunable. */
export const ADD_DROP_THRESHOLDS = { yes: 5, marginal: 1.5 }
/** Smallest DS-ceiling edge worth calling out. */
export const UPSIDE_NOTE_MIN = 2

export type Verdict = 'Yes' | 'Marginal' | 'No'

export interface AddDropAnalysis {
  status: 'ok' | 'insufficient'
  verdict: Verdict | null
  bestAdd: ComparisonPlayer | null
  /** Lowest-ROS-value drop candidate: who to drop if you do add. */
  dropTarget: ComparisonPlayer | null
  /** Best add's blended value minus drop target's. */
  gap: number | null
  upsideNote: string | null
  dropCaveat: string | null
}

const INSUFFICIENT: AddDropAnalysis = {
  status: 'insufficient', verdict: null, bestAdd: null, dropTarget: null, gap: null, upsideNote: null, dropCaveat: null,
}

function verdictFor(gap: number): Verdict {
  if (gap >= ADD_DROP_THRESHOLDS.yes) return 'Yes'
  if (gap >= ADD_DROP_THRESHOLDS.marginal) return 'Marginal'
  return 'No'
}

export function analyzeAddDrop(adds: ComparisonPlayer[], drops: ComparisonPlayer[]): AddDropAnalysis {
  const valuedAdds = adds.filter(p => p.blended != null)
  const valuedDrops = drops.filter(p => p.blended != null)
  if (valuedAdds.length === 0 || valuedDrops.length === 0) return INSUFFICIENT

  const bestAdd = valuedAdds.reduce((a, b) => ((b.blended as number) > (a.blended as number) ? b : a))
  const dropTarget = valuedDrops.reduce((a, b) => ((b.blended as number) < (a.blended as number) ? b : a))
  const gap = (bestAdd.blended as number) - (dropTarget.blended as number)

  // Upside: the add with the highest ceiling vs the drop target.
  let upsideNote: string | null = null
  const withCeiling = adds.filter(p => p.ceiling != null)
  if (withCeiling.length > 0 && dropTarget.ceiling != null) {
    const upsideAdd = withCeiling.reduce((a, b) => ((b.ceiling as number) > (a.ceiling as number) ? b : a))
    if ((upsideAdd.ceiling as number) - dropTarget.ceiling >= UPSIDE_NOTE_MIN) {
      upsideNote = `${upsideAdd.playerName} has the higher ceiling than ${dropTarget.playerName} (${round1(upsideAdd.ceiling as number)} vs ${round1(dropTarget.ceiling)}).`
    }
  }

  // Caveat: the suggested drop is lowest on ROS but has more upside than the add.
  let dropCaveat: string | null = null
  if (bestAdd.ceiling != null && dropTarget.ceiling != null && dropTarget.ceiling - bestAdd.ceiling >= UPSIDE_NOTE_MIN) {
    dropCaveat = `${dropTarget.playerName} is the lowest ROS value but has a higher ceiling than ${bestAdd.playerName} (${round1(dropTarget.ceiling)} vs ${round1(bestAdd.ceiling)}). Consider dropping someone else.`
  }

  return { status: 'ok', verdict: verdictFor(gap), bestAdd, dropTarget, gap, upsideNote, dropCaveat }
}

interface RowSpec {
  id: string
  label: string
  format: CellFormat
  better: 'higher' | 'lower' | null
  pick: (p: ComparisonPlayer, weekly: WeeklyPlayer | undefined) => number | string | null
}

const ROW_SPECS: RowSpec[] = [
  { id: 'blended', label: 'Blended ROS value', format: 'value', better: 'higher', pick: p => p.blended },
  { id: 'ceiling', label: 'DS ceiling (upside)', format: 'value', better: 'higher', pick: p => p.ceiling },
  { id: 'trend', label: 'ROS trend', format: 'signed', better: 'higher', pick: p => p.trend },
  // Direction of Draft Sharks' SOS percentage isn't documented: context only.
  { id: 'sos', label: 'Strength of schedule', format: 'text', better: null, pick: p => p.sos },
  { id: 'weekProjection', label: 'This week: DS projection', format: 'value', better: 'higher', pick: (_p, w) => (w && !w.isBye ? w.dsProjection : null) },
  { id: 'weekPositionRank', label: 'This week: position rank', format: 'rank', better: 'lower', pick: (_p, w) => (w && !w.isBye ? w.positionRank : null) },
  { id: 'weekFlexRank', label: 'This week: FLEX rank', format: 'rank', better: 'lower', pick: (_p, w) => (w && !w.isBye ? w.flexRank : null) },
]

/**
 * Row-based comparison across every selected player (adds and drops
 * together, so the best/worst highlight spans both lists).
 */
export function addDropRows(players: ComparisonPlayer[], weeklyByKey: Map<string, WeeklyPlayer>): ComparisonRow[] {
  const samePosition = new Set(players.map(p => p.position)).size <= 1
  return ROW_SPECS.map(spec => {
    const values = players.map(p => spec.pick(p, weeklyByKey.get(p.key)))
    const canHighlight = spec.better != null && spec.format !== 'text' && (spec.id !== 'weekPositionRank' || samePosition)
    const highlights = canHighlight
      ? highlightRow(values as (number | null)[], spec.better as 'higher' | 'lower')
      : values.map(() => null)
    return { id: spec.id, label: spec.label, format: spec.format, values, highlights }
  })
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/lib/addDrop.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add site/src/lib/addDrop.ts site/src/lib/addDrop.test.ts
git commit -m "Add Add/Drop calculation module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Start/Sit page

**Files:**
- Create: `src/pages/StartSit.tsx`

- [ ] **Step 1: Write the page**

Create `src/pages/StartSit.tsx`:

```tsx
import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useWeeklyRows } from '../lib/useWeeklyRows'
import { useComparisonPool } from '../lib/useComparisonPool'
import type { Scoring } from '../lib/useBlendedRos'
import { buildWeeklyPool, type WeeklyPlayer } from '../lib/weeklyPool'
import { formatCell } from '../lib/playerComparison'
import { recommendStartSit, startSitRows } from '../lib/startSit'

const MIN_PLAYERS = 2
const MAX_PLAYERS = 5

export default function StartSit() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const weekly = useWeeklyRows(scoring)
  // ROS value is context only, so it never blocks or fails the page.
  const ros = useComparisonPool(scoring)

  const pool = useMemo(() => buildWeeklyPool(weekly.rows), [weekly.rows])
  const rosByKey = useMemo(() => new Map(ros.pool.map(p => [p.key, p.blended])), [ros.pool])
  const byKey = useMemo(() => new Map(pool.map(p => [p.key, p])), [pool])

  const selected = useMemo(
    () => selectedKeys.map(k => byKey.get(k)).filter((p): p is WeeklyPlayer => !!p),
    [selectedKeys, byKey],
  )
  const candidates = useMemo(
    () => pool
      .filter(p => !selectedKeys.includes(p.key))
      .map(p => ({ key: p.key, playerName: p.playerName, position: p.position, team: p.team, blended: rosByKey.get(p.key) ?? null })),
    [pool, selectedKeys, rosByKey],
  )

  const rows = useMemo(() => startSitRows(selected, rosByKey), [selected, rosByKey])
  const rec = useMemo(() => recommendStartSit(selected), [selected])
  const starter = rec.starterKey ? byKey.get(rec.starterKey) : undefined

  const { loading, error } = weekly

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Start/Sit -- compare {MIN_PLAYERS}–{MAX_PLAYERS} players for this week's lineup.</span>
          <span className="btn btn-primary" style={{ cursor: 'default' }}>Week {weekly.week ?? '…'}</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {selected.length > 0 && <button className="btn ml-auto" onClick={() => setSelectedKeys([])}>Clear</button>}
          {weekly.freshest && <span className="subtle">Data as of {new Date(weekly.freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading weekly rankings…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}

        {!loading && !error && (
          <PlayerPicker
            candidates={candidates}
            disabled={selected.length >= MAX_PLAYERS}
            placeholder={selected.length >= MAX_PLAYERS ? `Max ${MAX_PLAYERS} players` : 'Add a player…'}
            onAdd={p => setSelectedKeys(prev => (prev.length >= MAX_PLAYERS ? prev : [...prev, p.key]))}
          />
        )}
      </div>

      {!loading && !error && selected.length > 0 && (
        <div className="card p-4 space-y-3">
          <ComparisonTable
            columns={selected.map(p => ({
              key: p.key,
              header: (
                <span>
                  {p.playerName}
                  {p.key === rec.starterKey && <span style={{ color: 'var(--signal-up)' }}> ✓ Start</span>}{' '}
                  <button
                    className="subtle"
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelectedKeys(prev => prev.filter(k => k !== p.key))}
                    aria-label={`Remove ${p.playerName}`}
                  >
                    ✕
                  </button>
                </span>
              ),
              subheader: `${p.position}${p.team ? ` · ${p.team}` : ''}${p.isBye ? ' · BYE' : ''}`,
            }))}
            rows={rows.map(r => ({
              id: r.id,
              label: r.label,
              cells: r.values.map((v, i) => ({ text: formatCell(v, r.format), highlight: r.highlights[i] })),
            }))}
          />
          <div className="subtle">
            The rank score is a weighted average of Draft Sharks, Boone and Smyth ranks. It is comparable across RB/WR/TE, which is what FLEX rank uses;
            position rank is only highlighted when everyone shares a position. Opponent and ROS value are context and don't affect the pick.
          </div>
        </div>
      )}

      {!loading && !error && rec.status === 'ok' && starter && (
        <div className="card p-4 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="label">Start</span>
            <span className="font-semibold">{starter.playerName}</span>
            <span className="subtle">{starter.position}{starter.team ? ` · ${starter.team}` : ''}</span>
            <span className="btn" style={{ cursor: 'default' }}>{rec.confidence}</span>
          </div>
          <ul className="list-disc pl-5 text-sm space-y-0.5">
            {rec.reasons.map(reason => <li key={reason}>{reason}</li>)}
          </ul>
          {rec.note && <div className="subtle">{rec.note}</div>}
        </div>
      )}

      {!loading && !error && selected.length > 0 && rec.status !== 'ok' && rec.note && (
        <div className="card p-4 subtle">{rec.note}</div>
      )}

      {!loading && !error && selected.length === 0 && (
        <div className="card p-4 subtle">Search for a player above to start comparing.</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `npx tsc -b`
Expected: no errors. (Page is not routed yet; wiring is Task 8.)

- [ ] **Step 3: Commit**

```bash
git add site/src/pages/StartSit.tsx
git commit -m "Add Start/Sit page

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Add/Drop page

**Files:**
- Create: `src/pages/AddDrop.tsx`

- [ ] **Step 1: Write the page**

Create `src/pages/AddDrop.tsx`:

```tsx
import { useMemo, useState } from 'react'
import PlayerPicker from '../components/PlayerPicker'
import ComparisonTable from '../components/ComparisonTable'
import ScoringToggle from '../components/ScoringToggle'
import { useComparisonPool } from '../lib/useComparisonPool'
import { useWeeklyRows } from '../lib/useWeeklyRows'
import type { Scoring } from '../lib/useBlendedRos'
import { buildWeeklyPool } from '../lib/weeklyPool'
import { formatCell, round1, type ComparisonPlayer } from '../lib/playerComparison'
import { addDropRows, analyzeAddDrop } from '../lib/addDrop'

const MAX_PER_LIST = 5

export default function AddDrop() {
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [addKeys, setAddKeys] = useState<string[]>([])
  const [dropKeys, setDropKeys] = useState<string[]>([])
  const { pool, freshest, loading, error } = useComparisonPool(scoring)
  // This week's outlook is secondary context, so it never blocks or fails the page.
  const weekly = useWeeklyRows(scoring)

  const byKey = useMemo(() => new Map(pool.map(p => [p.key, p])), [pool])
  const weeklyByKey = useMemo(() => new Map(buildWeeklyPool(weekly.rows).map(p => [p.key, p])), [weekly.rows])

  const resolve = (keys: string[]) => keys.map(k => byKey.get(k)).filter((p): p is ComparisonPlayer => !!p)
  const adds = useMemo(() => resolve(addKeys), [addKeys, byKey])
  const drops = useMemo(() => resolve(dropKeys), [dropKeys, byKey])
  const all = useMemo(() => [...adds, ...drops], [adds, drops])

  const candidates = useMemo(
    () => pool.filter(p => !addKeys.includes(p.key) && !dropKeys.includes(p.key)),
    [pool, addKeys, dropKeys],
  )

  const rows = useMemo(() => addDropRows(all, weeklyByKey), [all, weeklyByKey])
  const analysis = useMemo(() => analyzeAddDrop(adds, drops), [adds, drops])

  const remove = (key: string) => {
    setAddKeys(prev => prev.filter(k => k !== key))
    setDropKeys(prev => prev.filter(k => k !== key))
  }

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="subtle">Add/Drop -- is anyone worth adding, and who should go?</span>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {all.length > 0 && <button className="btn ml-auto" onClick={() => { setAddKeys([]); setDropKeys([]) }}>Clear</button>}
          {freshest && <span className="subtle">Data as of {new Date(freshest).toLocaleString()}</span>}
        </div>

        {loading && <div className="subtle">Loading player values…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}

        {!loading && !error && (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <span className="label">Add candidates (waiver wire)</span>
              <PlayerPicker
                candidates={candidates}
                disabled={adds.length >= MAX_PER_LIST}
                placeholder={adds.length >= MAX_PER_LIST ? `Max ${MAX_PER_LIST} adds` : 'Add a waiver player…'}
                onAdd={p => setAddKeys(prev => (prev.length >= MAX_PER_LIST ? prev : [...prev, p.key]))}
              />
            </div>
            <div className="space-y-1">
              <span className="label">Drop candidates (my bench)</span>
              <PlayerPicker
                candidates={candidates}
                disabled={drops.length >= MAX_PER_LIST}
                placeholder={drops.length >= MAX_PER_LIST ? `Max ${MAX_PER_LIST} drops` : 'Add a bench player…'}
                onAdd={p => setDropKeys(prev => (prev.length >= MAX_PER_LIST ? prev : [...prev, p.key]))}
              />
            </div>
          </div>
        )}
      </div>

      {!loading && !error && all.length > 0 && (
        <div className="card p-4 space-y-3">
          <ComparisonTable
            columns={all.map(p => ({
              key: p.key,
              header: (
                <span>
                  {p.playerName}{' '}
                  <button
                    className="subtle"
                    style={{ cursor: 'pointer' }}
                    onClick={() => remove(p.key)}
                    aria-label={`Remove ${p.playerName}`}
                  >
                    ✕
                  </button>
                </span>
              ),
              subheader: `${addKeys.includes(p.key) ? 'ADD' : 'DROP'} · ${p.position}${p.team ? ` · ${p.team}` : ''}`,
            }))}
            rows={rows.map(r => ({
              id: r.id,
              label: r.label,
              cells: r.values.map((v, i) => ({ text: formatCell(v, r.format), highlight: r.highlights[i] })),
            }))}
          />
          <div className="subtle">
            ROS value answers "who is better right now"; ceiling answers "who has the better best case". They are shown separately on purpose.
            This week's rows and strength of schedule are context only. Weekly position rank is highlighted only when everyone shares a position.
          </div>
        </div>
      )}

      {!loading && !error && analysis.status === 'ok' && analysis.bestAdd && analysis.dropTarget && (
        <div className="card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="label">1. Worth adding?</span>
              <span className="btn" style={{ cursor: 'default' }}>{analysis.verdict}</span>
            </div>
            <div>
              {analysis.bestAdd.playerName} ({round1(analysis.bestAdd.blended as number)}) vs {analysis.dropTarget.playerName} ({round1(analysis.dropTarget.blended as number)}):{' '}
              {(analysis.gap as number) > 0 ? '+' : ''}{round1(analysis.gap as number)} ROS value.
            </div>
            {analysis.upsideNote && <div className="subtle">{analysis.upsideNote}</div>}
          </div>
          <div className="space-y-1">
            <span className="label">2. If you add, drop</span>
            <div>{analysis.dropTarget.playerName} <span className="subtle">{analysis.dropTarget.position}{analysis.dropTarget.team ? ` · ${analysis.dropTarget.team}` : ''}</span></div>
            {analysis.dropCaveat && <div className="subtle">{analysis.dropCaveat}</div>}
          </div>
        </div>
      )}

      {!loading && !error && all.length > 0 && analysis.status === 'insufficient' && (
        <div className="card p-4 subtle">Pick at least one add candidate and one drop candidate to see a verdict.</div>
      )}

      {!loading && !error && all.length === 0 && (
        <div className="card p-4 subtle">Search for players above: waiver targets on the left, your bench on the right.</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add site/src/pages/AddDrop.tsx
git commit -m "Add Add/Drop page

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Navigation and routing

**Files:**
- Modify: `src/nav.ts`
- Modify: `src/pages/index.ts`
- Modify: `src/App.tsx`

- [ ] **Step 1: Edit `src/nav.ts`**

Replace the `PageId` line and `NAV_ITEMS` array so they read:

```ts
export type PageId = 'rankings' | 'tradevalues' | 'trade' | 'startsit' | 'adddrop' | 'movers' | 'disagreement' | 'compare'

export interface NavItem {
  id: PageId
  label: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'rankings', label: 'Rankings' },
  { id: 'tradevalues', label: 'Trade Values' },
  { id: 'trade', label: 'Trade Analyzer' },
  { id: 'startsit', label: 'Start/Sit' },
  { id: 'adddrop', label: 'Add/Drop' },
  { id: 'movers', label: 'Movers & Fallers' },
  { id: 'disagreement', label: 'Expert Disagreement' },
  { id: 'compare', label: 'Player Comparison' },
]
```
(Keep the file's header comment; update "Data Health, Start/Sit, etc." to "Data Health, Home, etc." since Start/Sit now exists.)

- [ ] **Step 2: Edit `src/pages/index.ts`**

Append:
```ts
export { default as StartSit } from './StartSit'
export { default as AddDrop } from './AddDrop'
```

- [ ] **Step 3: Edit `src/App.tsx`**

Change the import to
```tsx
import { Rankings, TradeValues, TradeAnalyzer, StartSit, AddDrop, MoversFallers, ExpertDisagreement, PlayerComparison } from './pages'
```
and add inside `<main>` after the `trade` line:
```tsx
          {page === 'startsit' && <StartSit />}
          {page === 'adddrop' && <AddDrop />}
```

- [ ] **Step 4: Type-check, test, commit**

Run: `npx tsc -b && npm test`
Expected: no errors; all tests pass.

```bash
git add site/src/nav.ts site/src/pages/index.ts site/src/App.tsx
git commit -m "Wire Start/Sit and Add/Drop into navigation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Verify both pages against live data

No code unless a check fails. Use `preview_start` with name `site`; prefer `read_page` / `get_page_text` over screenshots.

- [ ] **Step 1: Start/Sit**

Open Start/Sit. Check, and report what you actually saw:
1. The "Week N" badge shows a number and the picker loads (no "Failed to load").
2. Add two RBs (e.g. search "Bijan", "Gibbs" or any two names that resolve). The table shows rank score, position rank, FLEX rank, DS/Boone/Smyth ranks, DS projection/floor/ceiling, opponent, ROS value. A "✓ Start" marker and a Start card with a confidence chip and 1-2 reasons appear.
3. FLEX check: add an RB and a WR. A recommendation still appears and both show a FLEX rank.
4. QB guard: add a QB plus an RB. The Start card is replaced by the "QBs are ranked against QBs only" note, and no "✓ Start" appears.
5. Bye check, if any player is on a bye this week: the column shows "BYE", is excluded from the pick, and the note says so.
6. Sanity-check FLEX rank against the Rankings weekly tab for one RB: their ordering by Agg. Rank within a position should match their ordering by FLEX rank in Start/Sit.
7. `read_console_messages` shows no errors.

- [ ] **Step 2: Add/Drop**

Open Add/Drop. Add one or two players as adds and one or two as drops.
1. Columns are labeled ADD/DROP with position and team; rows show blended ROS value, ceiling, trend, SOS and the three "This week" rows (dashes for players with no weekly row).
2. The verdict card shows Yes/Marginal/No, the gap, and the "If you add, drop" line.
3. **Threshold sanity check:** read the blended-value scale from a few real players. `ADD_DROP_THRESHOLDS` (yes 5, marginal 1.5) and `UPSIDE_NOTE_MIN` (2) in `src/lib/addDrop.ts` were set without confirming the scale of `blended`/`ceiling`. If typical add-vs-bench gaps are e.g. 30+ points (so nearly everything reads "Yes") or under 1 (so nearly everything reads "No"), adjust those constants and the boundary tests in `addDrop.test.ts` (they reference the constants, so only edge fixtures may need touching), then re-run the tests. Do the same check for `CONFIDENCE_THRESHOLDS` in `startSit.ts` against real rank-score gaps.
4. Removing a player via ✕ updates the table and verdict; Clear empties everything.
5. `read_console_messages` shows no errors.

- [ ] **Step 3: Mobile width**

`resize_window` preset `mobile`; confirm both pages scroll their tables horizontally without breaking layout (the pickers stack on Add/Drop). Reset with preset `desktop` when done.

- [ ] **Step 4: Full suite, then commit any threshold tweaks**

Run: `npm test && npx tsc -b`
Expected: all pass. If constants changed:

```bash
git add site/src/lib/addDrop.ts site/src/lib/addDrop.test.ts site/src/lib/startSit.ts site/src/lib/startSit.test.ts
git commit -m "Tune Start/Sit and Add/Drop thresholds against live data

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Roadmap and README

**Files:**
- Modify: `SITE_ROADMAP.md` (repo root, `in-season/SITE_ROADMAP.md`)
- Modify: `site/README.md`

- [ ] **Step 1: Tick Start/Sit items in `SITE_ROADMAP.md` section 3**

Change `- [ ]` to `- [x]` on these lines (exact text):
- `Aggregate weekly rank — primary decision anchor`
- `Draft Sharks weekly rank`
- `Boone weekly rank`
- `Draft Sharks weekly projection`
- `Draft Sharks floor`
- `Draft Sharks ceiling`
- `ROS value/rank as secondary context`
- `Confidence level`
- every line under `## Behavior`
- under `## Recommendation Logic`: `Aggregate weekly rank is the anchor`, `Boone and Draft Sharks shown separately for transparency`, `Projection/floor/ceiling/matchup are supporting context`, `ROS context is secondary and should mainly help with "start your studs" situations`

Leave open: `Develop weighting model later`, `Backtest weighting against historical weekly outcomes`, `Tune weights after enough data exists`.

Change the matchup line to stay unchecked with a note:
`- [ ] Matchup rating — v1 shows the opponent (home/away) only; a real rating needs a data source`

Under the Start/Sit `## Recommendation Logic` block add one line:
`- v1 anchors on the weighted rank score (comparable across RB/WR/TE); a QB mixed with a non-QB gets no recommendation. FLEX rank is shown alongside position rank.`

- [ ] **Step 2: Tick Add/Drop items in section 5**

Tick every line under `## Must Have` (all nine). Leave the V2 and Waiver Wire items open.

- [ ] **Step 3: Update `site/README.md`**

Near line 16-17 (the Player Comparison bullet and the "Not yet built" sentence) add two bullets:

```md
- **Start/Sit** — compare 2–5 players for this week's lineup; recommends a starter from the weighted rank score (DS + Boone + Smyth) with High/Medium/Toss-up confidence, and shows position rank plus FLEX rank (RB/WR/TE ranked together). Logic in `src/lib/startSit.ts`, shared weekly shape in `src/lib/weeklyPool.ts`.
- **Add/Drop** — waiver candidates vs bench candidates; a two-step "worth adding?" (Yes/Marginal/No on blended ROS value gap) then "who to drop?" verdict, with DS ceiling kept as a separate upside axis. Logic in `src/lib/addDrop.ts`.
```
and change the sentence to `Not yet built: Home, Team Analyzer, Data Health.` Also change the "These four are v1s" wording to "These are v1s".

- [ ] **Step 4: Commit**

`site/README.md` and `SITE_ROADMAP.md` may already carry uncommitted edits that aren't part of this work. Run `git diff SITE_ROADMAP.md site/README.md` before staging; if there are unrelated hunks, stage only yours with `git add -p` rather than the whole file.

```bash
git add SITE_ROADMAP.md site/README.md
git commit -m "Update roadmap and README for Start/Sit and Add/Drop v1

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** matchup opponent-only (Task 4 `opponent` row, Task 10 roadmap note); score anchor + QB guard (Task 4); FLEX rank (Tasks 1, 4, 5); shared hook extractions (Tasks 2, 3); Start/Sit rows/recommendation/reasons/guards (Tasks 4, 6); Add/Drop pickers/columns/two-step analysis (Tasks 5, 7); wiring (Task 8); tests (Tasks 1, 3, 4, 5); dev-server verification incl. mobile (Task 9); roadmap/README (Task 10); commit scope (per-task file lists).
- **Known unknowns handled in the plan, not hidden:** the scale of `blended`/`ceiling`/rank-score gaps is unverified, so the thresholds are named constants with an explicit live-data check in Task 9. Bye detection uses "no opponent string" (DS emits an empty matchup for bye weeks per `docs/DATA.md`); if a bye-week player appears in Boone/Smyth only with an opponent, they won't be flagged.
- **Type consistency:** `WeeklyPlayer` (Task 1) is the single weekly shape used by `startSit.ts`, `addDrop.ts` and both pages; `ComparisonPlayer`/`ComparisonRow`/`highlightRow`/`round1`/`formatCell` all come from `playerComparison.ts`; `computeFlexRanks` lives in `weeklyPool.ts` (the spec allowed `blend.ts` or a small new module).
