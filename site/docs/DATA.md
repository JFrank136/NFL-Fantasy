# Data reference — Shambert's Lab site

This app is read-only against the shared "Fantasy Football" Supabase project (`tdtchffawcmkvgrccjza`). It does not write to Supabase — all writes come from the `in-season` Python pipeline (see `in-season/docs/DATA.md` for the pipeline side of this schema, scraper details, and raw table definitions). This file covers what the **site** reads and the business logic it applies on top.

## Tables/views read

| Table/view | Used by | Notes |
|---|---|---|
| `in_season_rankings_latest` | Rankings — Weekly tab, and current-week detection | `DISTINCT ON` view, still contains one row per (week, source, scoring, player) — filter by `week` explicitly, don't assume "latest" means one row per player. Draft Sharks publishes all 18 weeks at once; Boone/Smythe only publish the current week — current week is detected as the max week Boone/Smythe have data for. |
| `in_season_ros_rankings_latest` | Rankings — ROS tab | One row per (source, scoring, player) at the latest pull. `ds_value` is Draft Sharks' blended ROS trade value; `ceiling_proj` is their ROS ceiling/upside. |
| `in_season_ros_rankings` (raw, not `_latest`) | `useRosHistory.ts` (Rankings ROS Δ, Movers & Fallers) | Queried directly (not the `_latest` view), full history, paginated. `movers.ts` picks current/baseline snapshots from it. |
| `in_season_trade_values_latest` | Trade Values page, and Rankings ROS tab (Boone only) | 5 live sources as of 2026-09-17: `boone`, `cbs`, `fantasypros`, `rsj`, `usatoday`. **Draft Sharks trade values are not in this table** — Draft Sharks' ROS numbers live in `in_season_ros_rankings` instead, under a different shape. |
| `in_season_trade_values` (raw) | `useRosHistory.ts` | Same raw-vs-latest distinction as ROS rankings, filtered to `source = 'boone'`. Sources scrape per position and sometimes rerun one position, so pulls do NOT always share one `pulled_at` across positions — snapshots must be chosen per position (`splitSnapshots`), never as one global timestamp. |

## Boone trade-value column semantics

`in_season_trade_values` stores two generic columns (`value_col1`/`value_col2`) whose meaning depends on `position`:

- **RB/WR/TE**: `value_col1_label = 'HALF'`, `value_col2_label = 'PPR'` — pick based on the page's scoring toggle.
- **QB**: `value_col1_label = '1QB'`, `value_col2_label = '2QB'` — **always use `value_col1` (1QB) regardless of the scoring toggle**. Confirmed with Jared: 1QB is the correct equivalent for both Half-PPR and PPR at the QB position, so the PPR/Half-PPR toggle has no effect on QB rows by design, not by omission.

This mapping lives in `Rankings.tsx`'s `booneValueFor()` helper — if Boone's data ever adds a genuine QB PPR split, that function is where the special-casing goes.

## ROS blended value algorithm (`src/lib/blend.ts` → `blendRosValues`)

1. For the selected scoring format, build two maps keyed on `canonical_name` (already resolved server-side by the pipeline's `player_identity.py` for every source — the site never re-derives name matching).
2. Fit Boone's value onto Draft Sharks' scale via `robustLinearFit`/`applyScale` (`src/lib/regression.ts`, reused unchanged from the old CSV-era weekly blend engine) using players present in both sources.
3. Blend 50/50 for players present in both sources; use the single available value unblended for players present in only one.
4. Rank the result **across all positions together**, descending — confirmed with Jared that the ROS tab's "Overall rank" is a single cross-position ranking, not per-position (the position filter narrows visible rows without renumbering them).

## Weekly aggregate rank algorithm (`src/lib/blend.ts` → `aggregateWeeklyRanks`/`weightedAverageRank`)

Weighted average of each source's **position-rank** (not raw value — weekly data has no shared value scale across sources), using `src/lib/consensusWeights.ts`:

```
default: { draftsharks: 0.50, boone: 0.30, smythe: 0.20 }
QB:      { draftsharks: 0.40, boone: 0.40, smythe: 0.20 }
```

These are the same weights already tuned in `Draft/config/settings.yaml`'s `consensus.weights` (note the spelling difference: that file's yaml key is `smyth`, this pipeline's `source` column value is `smythe` — mapped explicitly, not automatically). If a source is missing a rank for a player, its weight is redistributed proportionally across the sources that do have one, rather than silently under-weighting the total. Result is ranked **within each position** (unlike the ROS tab's cross-position rank) ascending — lower weighted score is better.

## Known gaps

- `in_season_ros_rankings` only has two pulls of history as of 2026-09-18 — the previous-snapshot lookup degrades gracefully (shows "New" instead of a delta) when fewer than 2 pulls exist for a scoring format, but hasn't been exercised against a long history yet.
- No "Matchup rating" data source exists yet (only opponent name) — Weekly tab intentionally omits it rather than faking a value.
