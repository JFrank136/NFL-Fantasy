# Shambert's Lab

The in-season fantasy football site: live weekly rankings, rest-of-season (ROS) values, and trade values, sourced from the `in-season` pipeline via Supabase. Replaces the earlier CSV-upload "Team Analyzer" prototype entirely — there is no local upload flow anymore, all data comes from the shared Supabase project.

## Current state (as of the 2026-09-17/18 redesign)

- **Rankings** page: two tabs.
  - **ROS** — blended Draft Sharks + Boone rest-of-season value (see `docs/DATA.md` for the blend algorithm), individual source values, Draft Sharks ceiling/upside, and week-over-week change ("ROS Δ").
  - **Weekly** — aggregate weekly rank across Draft Sharks/Boone/Smythe (weighted per `docs/DATA.md`), individual source ranks, Draft Sharks projection/floor/ceiling, opponent.
  - Both tabs: search, position filter, scoring toggle (PPR/Half-PPR), sortable columns.
- **Trade Values** page: browses `in_season_trade_values` across all 5 live trade-value sources (Boone, CBS, FantasyPros, RSJ, USA Today), plus Draft Sharks' ROS "3D value" (`ds_value`) as a sixth column. Queries that can exceed Supabase's silent 1000-row cap go through `fetchAllRows` (`src/lib/supabase.ts`).
- Visual system: "Turf Bright" palette (see `src/index.css` CSS custom properties), sidebar nav on desktop, hamburger/drawer on mobile.
- **Trade Analyzer** — 1–4 players per side, winner decided by total blended ROS value with a Close/Medium/High confidence badge (thresholds in `tradeAnalyzer.ts`).
- **Movers & Fallers** — biggest ROS value changes by metric (blended/Boone/DS/DS ceiling) for "latest change" or "since last week"; shows a "not enough history" state instead of guessing when a source has no old-enough snapshot.
- **Expert Disagreement** — current Boone-vs-Draft Sharks gaps (Boone mapped onto the DS scale, players outside the top 150 in both sources hidden) and direction-of-movement disagreements.
- **Player Comparison** — 2–5 players side by side with best/worst highlighting; uses the shared `PlayerPicker` / `ComparisonTable` / `ScoringToggle` components in `src/components/`.
- These four are v1s built from `Fantasy Football/SITE_ROADMAP.md` (repo root), which is the source of truth and gets items checked off as they ship. Not yet built: Home, Start/Sit, Add/Drop, Team Analyzer, Data Health.

## Quick start

```bash
npm install
npm run dev
```

Requires a `.env` (copy `.env.example`) with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` for the shared "Fantasy Football" Supabase project — **the whole app fails to render without these** (the pages barrel eagerly imports the Supabase client). Same variables must be set in the Vercel project's Environment Variables for production, since `.env` is gitignored and never ships.

## Build & test

```bash
npm run build   # tsc -b && vite build
npm test        # vitest run -- covers the pure calculation modules in src/lib (blend, tradeValues, tradeAnalyzer, movers, disagreement, playerComparison)
npx tsc --noEmit
```

Deployed on Vercel, auto-deploys on push to `main`: https://nfl-fantasy-sigma.vercel.app

## Architecture notes

- `src/lib/blend.ts` — pure, unit-tested calculation functions (ROS value blending, weekly rank aggregation). No Supabase/React dependency; pages fetch rows and hand them to these functions.
- `src/lib/useRosHistory.ts` / `src/lib/movers.ts` — full append-only ROS history fetch, plus pure per-position current/baseline snapshot splitting and change math. Used by Rankings' "ROS Δ" and Movers & Fallers so they always agree.
- `src/lib/useBlendedRos.ts` — current blended ROS value fetch (Trade Analyzer). Also home of `toDsRosInput` / `toBooneRosInput`, the row mappers every ROS page shares.
- `src/lib/disagreement.ts`, `src/lib/playerComparison.ts`, `src/lib/tradeAnalyzer.ts` — pure logic for their pages. Tunable thresholds are exported constants (`FLAT_THRESHOLD`, `RELEVANCE_RANK_CUTOFF`, `CONFIDENCE_THRESHOLDS`, `TIMEFRAME_MIN_GAP_MS`) because the roadmap says they get retuned after a full season.
- `src/components/` — `PlayerPicker`, `ComparisonTable`, `ScoringToggle` shared across pages. Trade Analyzer, Movers & Fallers, Expert Disagreement, Rankings and Trade Values still carry their own local copies of the picker/toggle; migrate them when touched.
- `src/lib/consensusWeights.ts` — the source-weighting used for weekly rank aggregation, hand-copied from `Draft/config/settings.yaml`'s `consensus.weights` (not read live — if that file is retuned, update this one to match).
- `src/nav.ts` — single source of truth for site navigation (`NAV_ITEMS`), consumed by both `Sidebar` and `MobileNav`.

See `docs/DATA.md` for the Supabase schema this app reads and the blend/aggregation algorithms in detail.
