# Start/Sit and Add/Drop v1 pages

## Goal

Build the two remaining decision-tool pages from `SITE_ROADMAP.md` sections 3
(Start/Sit) and 5 (Add/Drop), reusing the shared `PlayerPicker` and
`ComparisonTable` components and the existing weekly/ROS data hooks.

## Non-goals

- Roster/team imports, league availability, Waiver Wire discovery (V2).
- Injury/news, ROS-driven recommendation logic, backtested weights.
- A real "matchup rating" (no data source; see Decisions).
- Any change to the pipeline, Supabase schema, or scrapers.
- Touching the uncommitted Trade Analyzer work in the working tree.

## Decisions (made with Jared, 2026-09-18)

1. **Matchup:** show the opponent (with home/away) only. It is never
   highlighted and never used in the recommendation. A real matchup rating
   waits for a data source and stays open on the roadmap.
2. **Recommendation anchor:** the weighted weekly rank score
   (`aggregateScore` from `blend.ts`, DS + Boone + Smyth). Before the
   per-position re-rank it is on a shared scale for RB/WR/TE because Boone/
   Smyth are pulled from Yahoo's `FLX` query and DS ranks overall. QBs are
   ranked against QBs only. Mixing a QB with a non-QB shows a "not
   comparable" note instead of a recommended starter.
3. **FLEX rank:** in addition to position rank, show each RB/WR/TE's rank
   among all RB/WR/TE that week by `aggregateScore` (computed over the whole
   weekly pool, not just the selected players). It gives context that
   position rank hides (e.g. RB4 vs RB6 can be 4th vs 20th in FLEX). QBs and
   bye-week players get none.

## Shared refactors (behavior-preserving)

- **`lib/useWeeklyRows.ts`:** extract the inline `useWeeklyTab` fetch from
  `pages/Rankings.tsx` (paginated `in_season_rankings_latest`, grouped by
  `identityKey`, run through `aggregateWeeklyRanks`). Rankings switches to it.
- **`lib/useComparisonPool.ts`:** extract the ROS pool build (blended values,
  trend, SOS, `buildComparisonPool`) from `pages/PlayerComparison.tsx`.
  PlayerComparison switches to it; Add/Drop reuses it.
- Add `flexRank` helpers to `lib/blend.ts` (or a small new module) computing
  FLEX rank over an `AggregatedWeeklyRow[]`.

## Start/Sit

`lib/startSit.ts` (pure, no React/Supabase) and `pages/StartSit.tsx`.

- **Picker:** 2-5 players from the current week's weekly pool. Scoring
  toggle, week, and data-freshness label as on other pages. Bye-week players
  (no opponent) are selectable but flagged "BYE" and never recommended.
- **Rows** (best/worst highlighted where direction is clear):
  aggregate weekly rank score (anchor), position rank, FLEX rank, DS rank,
  Boone rank, Smyth rank, DS projection, DS floor, DS ceiling, opponent
  (display only), blended ROS value (context only).
- **Recommendation:** lowest `aggregateScore` among non-bye players starts.
  Confidence by score gap to the runner-up, thresholds as named constants:
  High >= 5, Medium >= 2, else Toss-up.
- **Reasons:** 1-2 short lines from the largest differences (both sources
  agree, FLEX-rank gap, floor/ceiling tradeoff).
- **Guards:** fewer than 2 valid players -> prompt; QB mixed with non-QB ->
  no recommendation, explanatory note; bye players excluded from the
  recommendation.

## Add/Drop

`lib/addDrop.ts` (pure) and `pages/AddDrop.tsx`.

- **Two pickers:** "Add candidates" (waiver players) and "Drop candidates"
  (my bench), 1-5 each, any position, from the ROS pool. A player can't be
  in both lists.
- **Columns per player:** position, blended ROS value, DS ceiling (upside),
  ROS trend, SOS, and current-week outlook (weekly aggregate rank, FLEX rank,
  DS projection) as secondary context. ROS and upside stay separate axes;
  no combined score.
- **Step 1, worth adding?** Best add's blended ROS minus the weakest drop's
  blended ROS -> Yes / Marginal / No via configurable thresholds. A separate
  upside note when an add's ceiling clearly exceeds the drop's.
- **Step 2, who to drop?** Suggest the lowest-ROS drop candidate; caveat when
  a lower-ROS bench player has a higher ceiling than the add.
- No cross-position logic; Waiver Wire discovery is out of scope.

## Wiring

- `nav.ts`: add `startsit` and `adddrop` to `PageId` and `NAV_ITEMS`.
- `pages/index.ts` exports both; `App.tsx` routes them.
- `SITE_ROADMAP.md`: tick completed Start/Sit and Add/Drop items; leave
  matchup rating, backtesting, and V2 items open (note matchup rating is
  deferred pending a source).

## Testing

- Vitest suites for `startSit.ts` (recommendation, confidence boundaries,
  FLEX rank, QB-mixing guard, bye handling, reasons) and `addDrop.ts`
  (Yes/Marginal/No boundaries, drop suggestion, upside caveat, empty/missing
  values), mirroring `playerComparison.test.ts`.
- Existing Rankings and PlayerComparison behavior verified unchanged after
  the hook extractions (existing tests + dev-server check).
- Both pages exercised in the dev server (desktop and mobile width).

## Commit scope

Only feature files, tests, and docs. No `data/last_*.json` runtime state and
no changes to the in-progress Trade Analyzer files.
