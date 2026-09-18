# Site Redesign: Visual Shell + Rankings/Trade Values Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `in-season/site`'s pre-Supabase CSV-upload scaffold with a new "Turf Bright" visual design, a sidebar/drawer navigation shell, and real Supabase-backed Rankings (ROS + Weekly tabs) and Trade Values pages.

**Architecture:** A pure-function calculation layer (`src/lib/blend.ts`, `src/lib/consensusWeights.ts`) handles the ROS value blend and weekly rank aggregation, fully unit-tested in isolation from React/Supabase. The pages fetch raw rows from Supabase and hand them to that layer. Navigation becomes a small `NAV_ITEMS`-driven `Sidebar`/`MobileNav` pair sharing a `Brand` component, replacing the flat tab row. All CSV-upload-era code (`state/store.ts`, `lib/csv.ts`, `lib/vorp.ts`, and every component that only existed to serve them) is deleted outright.

**Tech Stack:** React 18 + TypeScript + Vite + Tailwind (existing), `@supabase/supabase-js` (existing), Vitest (new — this plan introduces the project's first test runner, scoped to the new pure calculation functions).

---

## Reference: exact schema for new Supabase interfaces

`in_season_ros_rankings` (from `supabase/migrations/0002_ros_rankings.sql`):
```
id bigint, season int, source text, scoring text, pulled_at timestamptz,
as_of_week int, source_player_id text, player_name text, canonical_name text,
team text | null, position text, rank int | null, tier_overall int | null,
tier_positional int | null, projection float | null, floor_proj float | null,
ceiling_proj float | null, ds_value float | null, strength_of_schedule text | null,
games_played int | null, injury_risk text | null, bye int | null, created_at timestamptz
```
There is a `in_season_ros_rankings_latest` view with the same columns, `DISTINCT ON (season, source, scoring, canonical_name)` ordered by `pulled_at DESC`.

`Draft/config/settings.yaml`'s `consensus.weights` (source of truth for aggregate weekly rank weighting):
```yaml
weights:
  default: { boone: 0.30, draftsharks: 0.50, smyth: 0.20 }
  QB:      { boone: 0.40, draftsharks: 0.40, smyth: 0.20 }
```
Note the naming mismatch: the Draft tool's yaml key is `smyth`, but this pipeline's `source` column value is `smythe`. Map explicitly, don't assume they match.

---

### Task 1: Add Vitest

**Files:**
- Modify: `in-season/site/package.json`
- Create: `in-season/site/vitest.config.ts`

- [ ] **Step 1: Install vitest**

Run:
```bash
cd "in-season/site" && npm install -D vitest
```
Expected: adds `vitest` under `devDependencies` in `package.json` and updates `package-lock.json`.

- [ ] **Step 2: Add the test script**

In `package.json`, add to `"scripts"`:
```json
"test": "vitest run"
```
Full `scripts` block becomes:
```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run"
},
```

- [ ] **Step 3: Add a minimal Vitest config**

Create `in-season/site/vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
  },
})
```

- [ ] **Step 4: Verify the test runner works with no tests yet**

Run: `cd "in-season/site" && npm test`
Expected: `No test files found` message, exit code may be non-zero (no tests is not a pass) — that's fine, this just confirms the command executes. Do not worry about exit code here; Task 3 adds the first real test.

- [ ] **Step 5: Commit**

```bash
cd "in-season/site"
git add package.json package-lock.json vitest.config.ts
git commit -m "Add vitest for testing pure calculation functions"
```

---

### Task 2: Consensus weights constant

**Files:**
- Create: `in-season/site/src/lib/consensusWeights.ts`

- [ ] **Step 1: Write the file**

```typescript
// src/lib/consensusWeights.ts
//
// Mirrors Draft/config/settings.yaml's `consensus.weights`, which is the
// already-tuned source-weighting used by the Draft tool's live draft board.
// Reused here (rather than inventing a new weighting) for the Weekly tab's
// "Aggregate weekly rank" column.
//
// NOTE: the Draft tool's yaml key is "smyth"; this pipeline's `source`
// column value for the same analyst is "smythe" -- SourceWeights below
// uses this project's spelling, mapped explicitly at the yaml boundary
// (there is no live yaml read here, this is a hand-copied snapshot -- if
// Draft/config/settings.yaml is retuned, update this file to match).

export interface SourceWeights {
  draftsharks: number
  boone: number
  smythe: number
}

export const CONSENSUS_WEIGHTS: Record<string, SourceWeights> = {
  default: { draftsharks: 0.50, boone: 0.30, smythe: 0.20 },
  QB: { draftsharks: 0.40, boone: 0.40, smythe: 0.20 },
}

export function weightsForPosition(position: string): SourceWeights {
  return CONSENSUS_WEIGHTS[position] ?? CONSENSUS_WEIGHTS.default
}
```

- [ ] **Step 2: Commit**

```bash
cd "in-season/site"
git add src/lib/consensusWeights.ts
git commit -m "Add consensus weights constant for weekly rank aggregation"
```

---

### Task 3: Blend/aggregation pure functions + unit tests

**Files:**
- Create: `in-season/site/src/lib/blend.ts`
- Create: `in-season/site/src/lib/blend.test.ts`

This is the core calculation logic from the spec: the ROS blended-value fit (reusing `robustLinearFit`/`applyScale` from the existing `src/lib/regression.ts`) and the Weekly tab's weighted rank aggregation. Both are pure functions — no Supabase, no React — so they're fully testable in isolation.

- [ ] **Step 1: Write the failing tests**

Create `in-season/site/src/lib/blend.test.ts`:
```typescript
import { describe, it, expect } from 'vitest'
import { blendRosValues, type RosSourceRow, type BooneRosRow } from './blend'
import { weightedAverageRank, aggregateWeeklyRanks, type WeeklyPlayerInput } from './blend'

describe('weightedAverageRank', () => {
  it('averages three sources using default (non-QB) weights', () => {
    // default weights: draftsharks 0.50, boone 0.30, smythe 0.20
    // ranks: DS=2, Boone=4, Smythe=3 -> 2*.5 + 4*.3 + 3*.2 = 1 + 1.2 + 0.6 = 2.8
    const result = weightedAverageRank('RB', { draftsharks: 2, boone: 4, smythe: 3 })
    expect(result).toBeCloseTo(2.8, 5)
  })

  it('uses QB weights for QB position', () => {
    // QB weights: draftsharks 0.40, boone 0.40, smythe 0.20
    // ranks: DS=1, Boone=2, Smythe=1 -> 1*.4 + 2*.4 + 1*.2 = 0.4 + 0.8 + 0.2 = 1.4
    const result = weightedAverageRank('QB', { draftsharks: 1, boone: 2, smythe: 1 })
    expect(result).toBeCloseTo(1.4, 5)
  })

  it('redistributes weight proportionally when a source is missing', () => {
    // default weights, smythe missing: DS=2 (0.5), Boone=4 (0.3), remaining
    // weight normalized over {0.5, 0.3} -> DS effective 0.625, Boone 0.375
    // 2*0.625 + 4*0.375 = 1.25 + 1.5 = 2.75
    const result = weightedAverageRank('RB', { draftsharks: 2, boone: 4, smythe: null })
    expect(result).toBeCloseTo(2.75, 5)
  })

  it('returns null when no source has a rank', () => {
    const result = weightedAverageRank('RB', { draftsharks: null, boone: null, smythe: null })
    expect(result).toBeNull()
  })
})

describe('aggregateWeeklyRanks', () => {
  it('re-ranks players within position by weighted score, best score = rank 1', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'a', playerName: 'A', position: 'RB', team: 'BUF', draftsharksRank: 3, booneRank: 3, smytheRank: 3, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'b', playerName: 'B', position: 'RB', team: 'MIA', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'c', playerName: 'C', position: 'RB', team: 'NYJ', draftsharksRank: 2, booneRank: 2, smytheRank: 2, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ A: 3, B: 1, C: 2 })
  })

  it('ranks positions independently', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'qb1', playerName: 'QB1', position: 'QB', team: 'BUF', draftsharksRank: 5, booneRank: 5, smytheRank: 5, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'rb1', playerName: 'RB1', position: 'RB', team: 'MIA', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ QB1: 1, RB1: 1 })
  })

  it('gives players missing from every source a null rank, sorted last', () => {
    const players: WeeklyPlayerInput[] = [
      { canonicalName: 'a', playerName: 'A', position: 'RB', team: 'BUF', draftsharksRank: 1, booneRank: 1, smytheRank: 1, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
      { canonicalName: 'b', playerName: 'B', position: 'RB', team: 'MIA', draftsharksRank: null, booneRank: null, smytheRank: null, dsProjection: null, dsFloor: null, dsCeiling: null, opponent: null },
    ]
    const result = aggregateWeeklyRanks(players)
    const byName = Object.fromEntries(result.map(r => [r.playerName, r.aggregateRank]))
    expect(byName).toEqual({ A: 1, B: null })
  })
})

describe('blendRosValues', () => {
  it('blends overlapping players 50/50 after fitting Boone onto the DS scale', () => {
    // Boone's scale is roughly 2x Draft Sharks' in this fixture, so the fit
    // should scale boone values close to ds values before blending.
    const ds: RosSourceRow[] = [
      { canonicalName: 'p1', playerName: 'P1', position: 'RB', team: 'BUF', dsValue: 50, ceiling: 20 },
      { canonicalName: 'p2', playerName: 'P2', position: 'RB', team: 'MIA', dsValue: 40, ceiling: 18 },
      { canonicalName: 'p3', playerName: 'P3', position: 'RB', team: 'NYJ', dsValue: 30, ceiling: 16 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'p1', position: 'RB', value: 100 },
      { canonicalName: 'p2', position: 'RB', value: 80 },
      { canonicalName: 'p3', position: 'RB', value: 60 },
    ]
    const result = blendRosValues(ds, boone)
    const p1 = result.find(r => r.canonicalName === 'p1')!
    expect(p1.dsValue).toBe(50)
    expect(p1.booneValue).toBe(100)
    // After fitting boone (100/80/60) onto ds (50/40/30) the scaled boone
    // value for p1 should land close to 50, so the blend stays close to 50.
    expect(p1.blendedValue).not.toBeNull()
    expect(p1.blendedValue!).toBeGreaterThan(40)
    expect(p1.blendedValue!).toBeLessThan(60)
  })

  it('falls back to the single available value when a player is only in one source', () => {
    const ds: RosSourceRow[] = [
      { canonicalName: 'ds-only', playerName: 'DS Only', position: 'WR', team: 'BUF', dsValue: 70, ceiling: 25 },
    ]
    const boone: BooneRosRow[] = [
      { canonicalName: 'boone-only', position: 'WR', value: 90 },
    ]
    const result = blendRosValues(ds, boone)
    const dsOnly = result.find(r => r.canonicalName === 'ds-only')!
    const booneOnly = result.find(r => r.canonicalName === 'boone-only')!
    expect(dsOnly.blendedValue).toBe(70)
    expect(booneOnly.blendedValue).toBe(90)
  })

  it('ranks cross-position by blended value, descending', () => {
    const ds: RosSourceRow[] = [
      { canonicalName: 'qb1', playerName: 'QB1', position: 'QB', team: 'BUF', dsValue: 90, ceiling: 30 },
      { canonicalName: 'rb1', playerName: 'RB1', position: 'RB', team: 'MIA', dsValue: 95, ceiling: 30 },
    ]
    const boone: BooneRosRow[] = []
    const result = blendRosValues(ds, boone)
    const byName = Object.fromEntries(result.map(r => [r.canonicalName, r.overallRank]))
    expect(byName).toEqual({ rb1: 1, qb1: 2 })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail (module doesn't exist yet)**

Run: `cd "in-season/site" && npm test`
Expected: FAIL — `Cannot find module './blend'` or similar.

- [ ] **Step 3: Write the implementation**

Create `in-season/site/src/lib/blend.ts`:
```typescript
// src/lib/blend.ts
//
// Pure calculation functions for the Rankings page. No Supabase, no React
// -- pages fetch rows and hand them to these functions. See
// docs/superpowers/specs/2026-09-17-site-redesign-shell-and-rankings-design.md
// for the product rationale behind each formula.

import { robustLinearFit, applyScale } from './regression'
import { weightsForPosition } from './consensusWeights'

// ---- ROS tab: blended value ----

export interface RosSourceRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  dsValue: number | null
  ceiling: number | null
}

export interface BooneRosRow {
  canonicalName: string
  position: string
  value: number | null
}

export interface BlendedRosRow {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  dsValue: number | null
  booneValue: number | null
  ceiling: number | null
  blendedValue: number | null
  overallRank: number | null
}

/**
 * Blends Draft Sharks' ds_value with Boone's matched ROS trade value.
 * Boone's scale is fit onto Draft Sharks' scale (via the existing
 * robustLinearFit/applyScale pair) using players present in both sources,
 * then the two are averaged 50/50. Players present in only one source use
 * that source's value unblended. Result is ranked cross-position by
 * blendedValue, descending (confirmed with Jared: "Overall rank" is a
 * single ranking across all positions, not per-position).
 */
export function blendRosValues(
  dsRows: RosSourceRow[],
  booneRows: BooneRosRow[],
): BlendedRosRow[] {
  const dsMap = new Map(dsRows.map(r => [r.canonicalName, r]))
  const booneMap = new Map(booneRows.map(r => [r.canonicalName, r]))

  const overlapping: { x: number; y: number }[] = []
  dsMap.forEach((ds, name) => {
    const boone = booneMap.get(name)
    if (ds.dsValue != null && boone?.value != null) {
      overlapping.push({ x: boone.value, y: ds.dsValue })
    }
  })
  const { a, b } = robustLinearFit(overlapping.map(p => p.x), overlapping.map(p => p.y))

  const allNames = new Set<string>([...dsMap.keys(), ...booneMap.keys()])
  const rows: BlendedRosRow[] = []
  allNames.forEach(name => {
    const ds = dsMap.get(name)
    const boone = booneMap.get(name)
    const scaledBoone = boone?.value != null ? applyScale(a, b, boone.value) : null

    let blendedValue: number | null
    if (ds?.dsValue != null && scaledBoone != null) {
      blendedValue = (ds.dsValue + scaledBoone) / 2
    } else if (ds?.dsValue != null) {
      blendedValue = ds.dsValue
    } else {
      blendedValue = scaledBoone
    }

    rows.push({
      canonicalName: name,
      playerName: ds?.playerName ?? name,
      position: ds?.position ?? boone?.position ?? '',
      team: ds?.team ?? null,
      dsValue: ds?.dsValue ?? null,
      booneValue: boone?.value ?? null,
      ceiling: ds?.ceiling ?? null,
      blendedValue,
      overallRank: null,
    })
  })

  rows.sort((r1, r2) => {
    if (r1.blendedValue == null) return 1
    if (r2.blendedValue == null) return -1
    return r2.blendedValue - r1.blendedValue
  })
  rows.forEach((row, i) => {
    row.overallRank = row.blendedValue != null ? i + 1 : null
  })

  return rows
}

// ---- Weekly tab: aggregate rank ----

export interface WeeklySourceRanks {
  draftsharks: number | null
  boone: number | null
  smythe: number | null
}

/**
 * Weighted average of each source's position-rank, using
 * consensusWeights.ts. A source missing a rank for this player has its
 * weight redistributed proportionally across the sources that do have one
 * (rather than left out, which would silently under-weight the total).
 */
export function weightedAverageRank(position: string, ranks: WeeklySourceRanks): number | null {
  const weights = weightsForPosition(position)
  const entries = (['draftsharks', 'boone', 'smythe'] as const)
    .map(source => ({ source, rank: ranks[source], weight: weights[source] }))
    .filter((e): e is { source: keyof WeeklySourceRanks; rank: number; weight: number } => e.rank != null)

  if (entries.length === 0) return null
  const totalWeight = entries.reduce((sum, e) => sum + e.weight, 0)
  if (totalWeight === 0) return null

  return entries.reduce((sum, e) => sum + e.rank * (e.weight / totalWeight), 0)
}

export interface WeeklyPlayerInput {
  canonicalName: string
  playerName: string
  position: string
  team: string | null
  draftsharksRank: number | null
  booneRank: number | null
  smytheRank: number | null
  dsProjection: number | null
  dsFloor: number | null
  dsCeiling: number | null
  opponent: string | null
}

export interface AggregatedWeeklyRow extends WeeklyPlayerInput {
  aggregateScore: number | null
  aggregateRank: number | null
}

/** Re-ranks weightedAverageRank's output within each position (ascending -- lower weighted rank score is better). */
export function aggregateWeeklyRanks(players: WeeklyPlayerInput[]): AggregatedWeeklyRow[] {
  const withScores: AggregatedWeeklyRow[] = players.map(p => ({
    ...p,
    aggregateScore: weightedAverageRank(p.position, {
      draftsharks: p.draftsharksRank,
      boone: p.booneRank,
      smythe: p.smytheRank,
    }),
    aggregateRank: null,
  }))

  const byPosition = new Map<string, AggregatedWeeklyRow[]>()
  withScores.forEach(row => {
    const list = byPosition.get(row.position) ?? []
    list.push(row)
    byPosition.set(row.position, list)
  })

  byPosition.forEach(list => {
    list.sort((r1, r2) => {
      if (r1.aggregateScore == null) return 1
      if (r2.aggregateScore == null) return -1
      return r1.aggregateScore - r2.aggregateScore
    })
    list.forEach((row, i) => {
      row.aggregateRank = row.aggregateScore != null ? i + 1 : null
    })
  })

  return withScores
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "in-season/site" && npm test`
Expected: all tests in `blend.test.ts` PASS.

- [ ] **Step 5: Commit**

```bash
cd "in-season/site"
git add src/lib/blend.ts src/lib/blend.test.ts
git commit -m "Add blended ROS value and aggregate weekly rank calculations"
```

---

### Task 4: Add RosRankingRow to the Supabase client + previous-snapshot helper

**Files:**
- Modify: `in-season/site/src/lib/supabase.ts`
- Create: `in-season/site/src/lib/rosHistory.ts`

- [ ] **Step 1: Add the RosRankingRow interface**

In `in-season/site/src/lib/supabase.ts`, add after `TradeValueLatestRow` (after line 64):
```typescript

// Row shape for in_season_ros_rankings_latest.
export interface RosRankingRow {
  id: number
  season: number
  source: string
  scoring: string
  pulled_at: string
  as_of_week: number
  source_player_id: string
  player_name: string
  canonical_name: string
  team: string | null
  position: string
  rank: number | null
  tier_overall: number | null
  tier_positional: number | null
  projection: number | null
  floor_proj: number | null
  ceiling_proj: number | null
  ds_value: number | null
  strength_of_schedule: string | null
  games_played: number | null
  injury_risk: string | null
  bye: number | null
}
```

- [ ] **Step 2: Write the previous-snapshot helper**

Create `in-season/site/src/lib/rosHistory.ts`:
```typescript
// src/lib/rosHistory.ts
//
// Fetches the ROS/trade-value snapshot immediately before the current one,
// for the ROS tab's "ROS change" column. Kept separate from blend.ts so
// that file stays pure/synchronous and independently testable.

import { supabase, type RosRankingRow, type TradeValueLatestRow } from './supabase'

/**
 * Returns Draft Sharks ROS rows and Boone trade-value rows from the most
 * recent pull *before* `currentPulledAt`, or null if no earlier pull
 * exists yet (e.g. the very first week of this pipeline running).
 */
export async function fetchPreviousRosSnapshot(
  scoring: 'half-ppr' | 'ppr',
  currentPulledAt: string,
): Promise<{ dsRows: RosRankingRow[]; booneRows: TradeValueLatestRow[] } | null> {
  const { data: priorPulls } = await supabase
    .from('in_season_ros_rankings')
    .select('pulled_at')
    .eq('scoring', scoring)
    .lt('pulled_at', currentPulledAt)
    .order('pulled_at', { ascending: false })
    .limit(1)

  const previousPulledAt = priorPulls?.[0]?.pulled_at
  if (!previousPulledAt) return null

  const { data: dsRows } = await supabase
    .from('in_season_ros_rankings')
    .select('*')
    .eq('scoring', scoring)
    .eq('pulled_at', previousPulledAt)

  const { data: priorTradeValuePulls } = await supabase
    .from('in_season_trade_values')
    .select('pulled_at')
    .eq('source', 'boone')
    .lt('pulled_at', currentPulledAt)
    .order('pulled_at', { ascending: false })
    .limit(1)

  const previousTradeValuePulledAt = priorTradeValuePulls?.[0]?.pulled_at
  let booneRows: TradeValueLatestRow[] = []
  if (previousTradeValuePulledAt) {
    const { data } = await supabase
      .from('in_season_trade_values')
      .select('*')
      .eq('source', 'boone')
      .eq('pulled_at', previousTradeValuePulledAt)
    booneRows = (data ?? []) as TradeValueLatestRow[]
  }

  return { dsRows: (dsRows ?? []) as RosRankingRow[], booneRows }
}
```

- [ ] **Step 3: Type-check**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd "in-season/site"
git add src/lib/supabase.ts src/lib/rosHistory.ts
git commit -m "Add RosRankingRow type and previous-snapshot fetch helper"
```

---

### Task 5: Turf Bright design tokens

**Files:**
- Modify: `in-season/site/src/index.css`

- [ ] **Step 1: Replace the color tokens and utility classes**

Read the current file first (`in-season/site/src/index.css`) to confirm exact current content, then replace the whole file with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --ring: #e8b23d;
  --bg-page: #1f4a3a;
  --bg-sidebar: #193c2f;
  --bg-card: #254f3e;
  --bg-card-border: #366b54;
  --text-primary: #fbf8ef;
  --text-secondary: #a9c9b8;
  --accent-gold: #e8b23d;
  --accent-gold-text: #241a03;
  --signal-up: #8fe0a8;
  --signal-down: #ec9186;
}

body {
  background: var(--bg-page);
  color: var(--text-primary);
}

.card {
  @apply rounded-xl border shadow;
  background: var(--bg-card);
  border-color: var(--bg-card-border);
}
.btn {
  @apply inline-flex items-center gap-2 px-3 py-2 rounded-lg border;
  background: var(--bg-card);
  border-color: var(--bg-card-border);
  color: var(--text-primary);
}
.btn:hover {
  filter: brightness(1.1);
}
.btn-primary {
  background: var(--accent-gold);
  color: var(--accent-gold-text);
  border-color: var(--accent-gold);
}
.input {
  @apply rounded-lg px-3 py-2 outline-none border;
  background: var(--bg-card);
  border-color: var(--bg-card-border);
  color: var(--text-primary);
}
.input:focus {
  box-shadow: 0 0 0 2px var(--ring);
}
.label {
  @apply text-sm font-medium uppercase tracking-wide;
  color: var(--text-secondary);
}
.table {
  @apply w-full text-sm;
}
.table th {
  @apply py-2 px-3 text-left text-xs uppercase tracking-wide;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--bg-card-border);
}
.table td {
  @apply py-2 px-3;
  border-bottom: 1px solid var(--bg-card-border);
}
.badge {
  @apply inline-flex items-center px-2 py-0.5 rounded-md text-xs border;
  background: var(--bg-card);
  border-color: var(--bg-card-border);
}
.subtle {
  color: var(--text-secondary);
  @apply text-sm;
}
.link {
  color: var(--accent-gold);
}
.link:hover {
  text-decoration: underline;
}
.signal-up {
  color: var(--signal-up);
}
.signal-down {
  color: var(--signal-down);
}

/* Navigation */
.nav-item {
  @apply block w-full text-left px-3 py-2 rounded-lg text-sm font-semibold;
  color: var(--text-secondary);
}
.nav-item:hover {
  background: var(--bg-card);
}
.nav-item-active {
  background: var(--accent-gold);
  color: var(--accent-gold-text);
}
```

- [ ] **Step 2: Visually verify with the dev server**

Run: `cd "in-season/site" && npm run dev` (or use the project's preview tooling)
Open the site. Expected: background is turf-green, existing (not-yet-restyled) tab bar and tables still render without errors — colors will look inconsistent until later tasks restyle the components themselves, that's expected at this point. Confirm there are no console errors from the CSS change alone.

- [ ] **Step 3: Commit**

```bash
cd "in-season/site"
git add src/index.css
git commit -m "Replace design tokens with Turf Bright palette"
```

---

### Task 6: Brand, Sidebar, and MobileNav components

**Files:**
- Create: `in-season/site/src/components/Brand.tsx`
- Create: `in-season/site/src/components/Sidebar.tsx`
- Create: `in-season/site/src/components/MobileNav.tsx`
- Create: `in-season/site/src/nav.ts`

- [ ] **Step 1: Define the shared nav item list**

Create `in-season/site/src/nav.ts`:
```typescript
// src/nav.ts
//
// Single source of truth for site navigation, consumed by both Sidebar
// (desktop) and MobileNav (mobile drawer). Adding a future roadmap page
// (Data Health, Start/Sit, etc.) is a one-line addition here.

export type PageId = 'rankings' | 'tradevalues'

export interface NavItem {
  id: PageId
  label: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'rankings', label: 'Rankings' },
  { id: 'tradevalues', label: 'Trade Values' },
]
```

- [ ] **Step 2: Write the Brand component**

Create `in-season/site/src/components/Brand.tsx`:
```typescript
// src/components/Brand.tsx
export default function Brand() {
  return (
    <div className="flex items-center gap-2 font-extrabold text-sm uppercase tracking-wide" style={{ color: 'var(--text-primary)' }}>
      <span>🐱</span>
      <span>Shambert's Lab</span>
    </div>
  )
}
```

- [ ] **Step 3: Write the Sidebar component**

Create `in-season/site/src/components/Sidebar.tsx`:
```typescript
// src/components/Sidebar.tsx
import Brand from './Brand'
import { NAV_ITEMS, type PageId } from '../nav'

interface SidebarProps {
  active: PageId
  onSelect: (id: PageId) => void
}

export default function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside
      className="hidden md:flex md:flex-col md:w-48 md:shrink-0 md:h-screen md:sticky md:top-0 px-3 py-4 gap-1 border-r"
      style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--bg-card-border)' }}
    >
      <div className="px-3 pb-4">
        <Brand />
      </div>
      {NAV_ITEMS.map(item => (
        <button
          key={item.id}
          className={`nav-item ${active === item.id ? 'nav-item-active' : ''}`}
          onClick={() => onSelect(item.id)}
        >
          {item.label}
        </button>
      ))}
    </aside>
  )
}
```

- [ ] **Step 4: Write the MobileNav component**

Create `in-season/site/src/components/MobileNav.tsx`:
```typescript
// src/components/MobileNav.tsx
import { useState } from 'react'
import Brand from './Brand'
import { NAV_ITEMS, type PageId } from '../nav'

interface MobileNavProps {
  active: PageId
  onSelect: (id: PageId) => void
}

export default function MobileNav({ active, onSelect }: MobileNavProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="md:hidden">
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--bg-card-border)' }}
      >
        <Brand />
        <button
          aria-label={open ? 'Close menu' : 'Open menu'}
          className="text-2xl leading-none"
          style={{ color: 'var(--text-primary)' }}
          onClick={() => setOpen(o => !o)}
        >
          ☰
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div
            className="absolute top-0 left-0 bottom-0 w-64 p-4 flex flex-col gap-1"
            style={{ background: 'var(--bg-sidebar)' }}
          >
            <div className="px-3 pb-4">
              <Brand />
            </div>
            {NAV_ITEMS.map(item => (
              <button
                key={item.id}
                className={`nav-item ${active === item.id ? 'nav-item-active' : ''}`}
                onClick={() => {
                  onSelect(item.id)
                  setOpen(false)
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Type-check**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors (these components aren't wired into `App.tsx` yet, but should type-check standalone).

- [ ] **Step 6: Commit**

```bash
cd "in-season/site"
git add src/nav.ts src/components/Brand.tsx src/components/Sidebar.tsx src/components/MobileNav.tsx
git commit -m "Add Brand, Sidebar, and MobileNav shell components"
```

---

### Task 7: Delete the legacy CSV-upload scaffold

**Files:**
- Delete: `in-season/site/src/pages/Players.tsx`
- Delete: `in-season/site/src/pages/Trends.tsx`
- Delete: `in-season/site/src/pages/Roster.tsx`
- Delete: `in-season/site/src/pages/Trade.tsx`
- Delete: `in-season/site/src/pages/Weeks.tsx`
- Delete: `in-season/site/src/pages/Settings.tsx`
- Delete: `in-season/site/src/components/PlayersTable.tsx`
- Delete: `in-season/site/src/components/TrendsView.tsx`
- Delete: `in-season/site/src/components/RosterAnalyzer.tsx`
- Delete: `in-season/site/src/components/TradeSandbox.tsx`
- Delete: `in-season/site/src/components/WeekManager.tsx`
- Delete: `in-season/site/src/components/BlendEngine.tsx`
- Delete: `in-season/site/src/components/Settings.tsx`
- Delete: `in-season/site/src/components/Header.tsx`
- Delete: `in-season/site/src/state/store.ts`
- Delete: `in-season/site/src/lib/csv.ts`
- Delete: `in-season/site/src/lib/vorp.ts`
- Modify: `in-season/site/src/pages/index.ts`

This was confirmed safe by grepping the codebase: every one of these files is either dead (only imported by another file on this delete list) or was the sole consumer of `state/store.ts`/`lib/csv.ts`/`lib/vorp.ts`. `App.tsx` is rewritten in Task 8 to stop referencing any of them.

- [ ] **Step 1: Delete the files**

```bash
cd "in-season/site"
rm src/pages/Players.tsx src/pages/Trends.tsx src/pages/Roster.tsx src/pages/Trade.tsx src/pages/Weeks.tsx src/pages/Settings.tsx
rm src/components/PlayersTable.tsx src/components/TrendsView.tsx src/components/RosterAnalyzer.tsx src/components/TradeSandbox.tsx src/components/WeekManager.tsx src/components/BlendEngine.tsx src/components/Settings.tsx src/components/Header.tsx
rm src/state/store.ts src/lib/csv.ts src/lib/vorp.ts
rmdir src/state 2>/dev/null || true
```

- [ ] **Step 2: Update the pages barrel file**

Replace `in-season/site/src/pages/index.ts` entirely with:
```typescript
export { default as Rankings }    from './Rankings'
export { default as TradeValues } from './TradeValues'
```

- [ ] **Step 3: Confirm nothing else references the deleted files**

Run: `cd "in-season/site" && grep -rn "state/store\|lib/csv\|lib/vorp\|components/Header\|components/BlendEngine\|components/PlayersTable\|components/TrendsView\|components/RosterAnalyzer\|components/TradeSandbox\|components/WeekManager\|components/Settings\|pages/Players\|pages/Trends\|pages/Roster\|pages/Trade'\|pages/Weeks\|pages/Settings" src/`
Expected: no output (App.tsx is fixed in the next task, so it's fine if this greps clean already or still shows App.tsx — Task 8 removes those references).

- [ ] **Step 4: Commit**

```bash
cd "in-season/site"
git add -A
git commit -m "Delete pre-Supabase CSV-upload scaffold"
```

Note: `npx tsc --noEmit` will fail after this step because `App.tsx` still imports the deleted files — that's expected and fixed in Task 8. Don't run the type-check gate until after Task 8.

---

### Task 8: Rewrite App.tsx to use the new shell

**Files:**
- Modify: `in-season/site/src/App.tsx`

- [ ] **Step 1: Replace the file**

Replace `in-season/site/src/App.tsx` entirely with:
```typescript
// src/App.tsx
import { useState } from 'react'
import Sidebar from './components/Sidebar'
import MobileNav from './components/MobileNav'
import { Rankings, TradeValues } from './pages'
import type { PageId } from './nav'

export default function App() {
  const [page, setPage] = useState<PageId>('rankings')

  return (
    <div className="md:flex min-h-screen">
      <Sidebar active={page} onSelect={setPage} />
      <div className="flex-1 flex flex-col">
        <MobileNav active={page} onSelect={setPage} />
        <main className="flex-1 max-w-6xl w-full mx-auto p-4 space-y-4">
          {page === 'rankings' && <Rankings />}
          {page === 'tradevalues' && <TradeValues />}
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check the whole project**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors. (This is the gate deferred from Task 7 — it should be clean now.)

- [ ] **Step 3: Verify in the browser**

Start the dev server (`npm run dev` or the project's preview tooling) and confirm:
- Desktop width: sidebar visible on the left with "🐱 Shambert's Lab" and Rankings/Trade Values links, gold highlight on the active page.
- Resize to mobile width (<768px): sidebar disappears, a top bar with the hamburger icon appears; tapping it opens the drawer with the same two links; tapping a link navigates and closes the drawer.
- No console errors.

- [ ] **Step 4: Commit**

```bash
cd "in-season/site"
git add src/App.tsx
git commit -m "Rewrite App.tsx to use the Sidebar/MobileNav shell"
```

---

### Task 9: Rebuild the Rankings page (ROS + Weekly tabs)

**Files:**
- Modify: `in-season/site/src/pages/Rankings.tsx` (full rewrite)

This replaces last session's single-table Rankings page with the two-tab version from the spec. It reuses the existing week-detection logic (Boone/Smythe define "current week") for the Weekly tab, and adds the ROS tab backed by `blendRosValues`/`fetchPreviousRosSnapshot`.

- [ ] **Step 1: Replace the file**

Replace `in-season/site/src/pages/Rankings.tsx` entirely with:
```typescript
import { useEffect, useMemo, useState } from 'react'
import { supabase, type RankingLatestRow, type RosRankingRow, type TradeValueLatestRow } from '../lib/supabase'
import { blendRosValues, aggregateWeeklyRanks, type BlendedRosRow, type AggregatedWeeklyRow } from '../lib/blend'
import { fetchPreviousRosSnapshot } from '../lib/rosHistory'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
type Scoring = typeof SCORINGS[number]

type RosTabRow = BlendedRosRow & { rosChange: number | null }

function useCurrentWeek() {
  const [week, setWeek] = useState<number | null>(null)
  const [weeks] = useState<number[]>(Array.from({ length: 18 }, (_, i) => i + 1))

  useEffect(() => {
    let cancelled = false
    supabase
      .from('in_season_rankings_latest')
      .select('week')
      .in('source', ['boone', 'smythe'])
      .order('week', { ascending: false })
      .limit(1)
      .then(({ data }) => {
        if (!cancelled) setWeek(data?.[0]?.week ?? null)
      })
    return () => { cancelled = true }
  }, [])

  return { week, weeks }
}

function useRosTab(scoring: Scoring) {
  const [rows, setRows] = useState<RosTabRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      supabase.from('in_season_ros_rankings_latest').select('*').eq('scoring', scoring),
      supabase.from('in_season_trade_values_latest').select('*').eq('source', 'boone'),
    ]).then(async ([dsRes, booneRes]) => {
      if (cancelled) return
      if (dsRes.error) { setError(dsRes.error.message); setLoading(false); return }
      if (booneRes.error) { setError(booneRes.error.message); setLoading(false); return }

      const dsRows = (dsRes.data ?? []) as RosRankingRow[]
      const booneRows = (booneRes.data ?? []) as TradeValueLatestRow[]
      const currentPulledAt = dsRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), dsRows[0]?.pulled_at ?? '')

      const booneValueFor = (r: TradeValueLatestRow) =>
        r.position === 'QB' ? r.value_col1 : (scoring === 'ppr' ? r.value_col2 : r.value_col1)

      const blended = blendRosValues(
        dsRows.map(r => ({
          canonicalName: r.canonical_name, playerName: r.player_name, position: r.position,
          team: r.team, dsValue: r.ds_value, ceiling: r.ceiling_proj,
        })),
        booneRows.map(r => ({ canonicalName: r.canonical_name, position: r.position, value: booneValueFor(r) })),
      )

      let previousBlendedByName = new Map<string, number | null>()
      if (currentPulledAt) {
        const previous = await fetchPreviousRosSnapshot(scoring, currentPulledAt)
        if (previous) {
          const previousBlended = blendRosValues(
            previous.dsRows.map(r => ({
              canonicalName: r.canonical_name, playerName: r.player_name, position: r.position,
              team: r.team, dsValue: r.ds_value, ceiling: r.ceiling_proj,
            })),
            previous.booneRows.map(r => ({ canonicalName: r.canonical_name, position: r.position, value: booneValueFor(r) })),
          )
          previousBlendedByName = new Map(previousBlended.map(r => [r.canonicalName, r.blendedValue]))
        }
      }

      if (cancelled) return
      setRows(blended.map(r => {
        const prev = previousBlendedByName.get(r.canonicalName)
        const rosChange = r.blendedValue != null && prev != null ? r.blendedValue - prev : null
        return { ...r, rosChange }
      }))
      setFreshest(currentPulledAt || null)
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [scoring])

  return { rows, loading, error, freshest }
}

function useWeeklyTab(scoring: Scoring, week: number | null) {
  const [rows, setRows] = useState<AggregatedWeeklyRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshest, setFreshest] = useState<string | null>(null)

  useEffect(() => {
    if (week == null) return
    let cancelled = false
    setLoading(true)
    setError(null)

    supabase
      .from('in_season_rankings_latest')
      .select('*')
      .eq('scoring', scoring)
      .eq('week', week)
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) { setError(error.message); setLoading(false); return }

        const rankingRows = (data ?? []) as RankingLatestRow[]
        const byPlayer = new Map<string, RankingLatestRow[]>()
        rankingRows.forEach(r => {
          const list = byPlayer.get(r.canonical_name) ?? []
          list.push(r)
          byPlayer.set(r.canonical_name, list)
        })

        const players = Array.from(byPlayer.entries()).map(([canonicalName, sourceRows]) => {
          const ds = sourceRows.find(r => r.source === 'draftsharks')
          const boone = sourceRows.find(r => r.source === 'boone')
          const smythe = sourceRows.find(r => r.source === 'smythe')
          const any = ds ?? boone ?? smythe ?? sourceRows[0]
          return {
            canonicalName,
            playerName: any.player_name,
            position: any.position,
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
  }, [scoring, week])

  return { rows, loading, error, freshest }
}

export default function Rankings() {
  const [tab, setTab] = useState<'ros' | 'weekly'>('ros')
  const [pos, setPos] = useState('ALL')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [query, setQuery] = useState('')

  const { week, weeks } = useCurrentWeek()
  const ros = useRosTab(scoring)
  const weekly = useWeeklyTab(scoring, week)

  const active = tab === 'ros' ? ros : weekly

  const filteredRos = useMemo(() => {
    let list = ros.rows
    if (pos !== 'ALL') list = list.filter(r => r.position === pos)
    if (query) list = list.filter(r => r.playerName.toLowerCase().includes(query.toLowerCase()))
    return list
  }, [ros.rows, pos, query])

  const filteredWeekly = useMemo(() => {
    let list = weekly.rows
    if (pos !== 'ALL') list = list.filter(r => r.position === pos)
    if (query) list = list.filter(r => r.playerName.toLowerCase().includes(query.toLowerCase()))
    return list
  }, [weekly.rows, pos, query])

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button className={`btn ${tab === 'ros' ? 'btn-primary' : ''}`} onClick={() => setTab('ros')}>ROS</button>
        <button className={`btn ${tab === 'weekly' ? 'btn-primary' : ''}`} onClick={() => setTab('weekly')}>Weekly</button>
      </div>

      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <input className="input" placeholder="Search players..." value={query} onChange={e => setQuery(e.target.value)} />
          <select className="input" value={pos} onChange={e => setPos(e.target.value)}>
            {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="input" value={scoring} onChange={e => setScoring(e.target.value as Scoring)}>
            {SCORINGS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {tab === 'weekly' && (
            <select className="input" value={week ?? ''} onChange={() => {}} disabled>
              <option value={week ?? ''}>Week {week ?? '…'}</option>
            </select>
          )}
          {active.freshest && <span className="subtle ml-auto">Data as of {new Date(active.freshest).toLocaleString()}</span>}
        </div>

        {active.loading && <div className="subtle">Loading…</div>}
        {active.error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {active.error}</div>}

        {!active.loading && !active.error && tab === 'ros' && (
          <table className="table">
            <thead>
              <tr>
                <th>Rank</th><th>Player</th><th>Pos</th><th>Team</th>
                <th>Blended</th><th>DS Value</th><th>Boone Value</th><th>DS Ceiling</th><th>ROS Δ</th>
              </tr>
            </thead>
            <tbody>
              {filteredRos.map(r => (
                <tr key={r.canonicalName}>
                  <td>{r.overallRank ?? ''}</td>
                  <td>{r.playerName}</td>
                  <td>{r.position}</td>
                  <td>{r.team ?? ''}</td>
                  <td className="text-right font-semibold">{r.blendedValue != null ? Math.round(r.blendedValue) : ''}</td>
                  <td className="text-right">{r.dsValue ?? ''}</td>
                  <td className="text-right">{r.booneValue ?? ''}</td>
                  <td className="text-right">{r.ceiling ?? ''}</td>
                  <td className="text-right">
                    {r.rosChange == null
                      ? <span className="subtle">New</span>
                      : <span className={r.rosChange >= 0 ? 'signal-up' : 'signal-down'}>{r.rosChange >= 0 ? '+' : ''}{Math.round(r.rosChange)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!active.loading && !active.error && tab === 'weekly' && (
          <table className="table">
            <thead>
              <tr>
                <th>Agg. Rank</th><th>Player</th><th>Pos</th><th>Team</th>
                <th>DS Rank</th><th>Boone Rank</th><th>DS Proj</th><th>Floor</th><th>Ceiling</th><th>Opp</th>
              </tr>
            </thead>
            <tbody>
              {filteredWeekly.map(r => (
                <tr key={r.canonicalName}>
                  <td>{r.aggregateRank ?? ''}</td>
                  <td>{r.playerName}</td>
                  <td>{r.position}</td>
                  <td>{r.team ?? ''}</td>
                  <td className="text-right">{r.draftsharksRank ?? ''}</td>
                  <td className="text-right">{r.booneRank ?? ''}</td>
                  <td className="text-right">{r.dsProjection ?? ''}</td>
                  <td className="text-right">{r.dsFloor ?? ''}</td>
                  <td className="text-right">{r.dsCeiling ?? ''}</td>
                  <td>{r.opponent ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!active.loading && !active.error && (tab === 'ros' ? filteredRos : filteredWeekly).length === 0 && (
          <div className="subtle">No rows match these filters.</div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Verify in the browser**

Start the dev server and check:
- ROS tab (default): table populates with real Draft Sharks + Boone blended values, "ROS Δ" column shows "New" for every row (expected — only one week of ROS history exists as of this plan, per the spec's noted risk).
- Switch to Weekly tab: table populates with aggregate rank + DS/Boone individual ranks for the current week.
- Position filter and search both narrow the visible rows on both tabs.
- Scoring toggle (ppr/half-ppr) changes the values shown.
- No console errors.

- [ ] **Step 4: Commit**

```bash
cd "in-season/site"
git add src/pages/Rankings.tsx
git commit -m "Rebuild Rankings page with ROS and Weekly tabs backed by blend.ts"
```

---

### Task 10: Update Trade Values page (5 sources + restyle)

**Files:**
- Modify: `in-season/site/src/pages/TradeValues.tsx`

- [ ] **Step 1: Update the sources list and restyle the tab buttons**

In `in-season/site/src/pages/TradeValues.tsx`, change line 5 from:
```typescript
const SOURCES = ['ALL', 'draftsharks', 'boone']
```
to:
```typescript
const SOURCES = ['ALL', 'boone', 'cbs', 'fantasypros', 'rsj', 'usatoday']
```
(Draft Sharks trade values were never a real source here — only Boone/CBS/FantasyPros/RSJ/USA Today publish this trade-value table shape; Draft Sharks' ROS data lives in `in_season_ros_rankings` instead, consumed by the Rankings page.)

No other logic changes are needed — this page already queries `in_season_trade_values_latest` generically by `source`, and already uses the shared `.card`/`.input`/`.table` classes that Task 5 restyled. Confirm visually rather than editing markup blindly.

- [ ] **Step 2: Type-check**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Verify in the browser**

Navigate to the Trade Values page. Confirm:
- Source dropdown lists All/Boone/CBS/FantasyPros/RSJ/USA Today.
- Selecting each source shows real rows (all 5 have live data as of 2026-09-17's pipeline run).
- Page uses the Turf Bright palette (inherited from Task 5's CSS changes, no manual restyling needed here).

- [ ] **Step 4: Commit**

```bash
cd "in-season/site"
git add src/pages/TradeValues.tsx
git commit -m "Add CBS/FantasyPros/RSJ/USA Today to Trade Values source filter"
```

---

### Task 11: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd "in-season/site" && npm test`
Expected: all `blend.test.ts` tests PASS.

- [ ] **Step 2: Run the full type-check**

Run: `cd "in-season/site" && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Full manual walkthrough**

With the dev server running, walk through:
1. Desktop width (≥768px): sidebar present, Rankings/Trade Values navigable, active page highlighted gold.
2. Mobile width (<768px, use browser responsive mode or resize_window): hamburger + drawer works, closes on selection.
3. Rankings ROS tab: real blended values, position filter, search, scoring toggle, "ROS Δ" shows "New" (expected, single-snapshot state).
4. Rankings Weekly tab: real aggregate ranks, DS/Boone individual columns, position filter, search, scoring toggle.
5. Trade Values: all 5 sources selectable and populated.
6. No console errors on any page/viewport combination.
7. No dead links to deleted pages anywhere (nav only shows Rankings/Trade Values).

- [ ] **Step 4: Push**

```bash
cd "in-season/site"
git push origin main
```

Note: confirm with Jared before this push per this project's established norm of confirming pushes to the shared repo (Vercel auto-deploys from `main`).

---

## Deferred to a later spec (per SITE_ROADMAP.md, explicitly out of scope here)

Home, Start/Sit, Player Comparison, Add/Drop, Trade Analyzer, Movers & Fallers, Expert Disagreement, Team Analyzer, Data Health.
