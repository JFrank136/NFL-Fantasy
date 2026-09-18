# Shambert's Lab

The in-season fantasy football site: live weekly rankings, rest-of-season (ROS) values, and trade values, sourced from the `in-season` pipeline via Supabase. Replaces the earlier CSV-upload "Team Analyzer" prototype entirely — there is no local upload flow anymore, all data comes from the shared Supabase project.

## Current state (as of the 2026-09-17/18 redesign)

- **Rankings** page: two tabs.
  - **ROS** — blended Draft Sharks + Boone rest-of-season value (see `docs/DATA.md` for the blend algorithm), individual source values, Draft Sharks ceiling/upside, and week-over-week change ("ROS Δ").
  - **Weekly** — aggregate weekly rank across Draft Sharks/Boone/Smythe (weighted per `docs/DATA.md`), individual source ranks, Draft Sharks projection/floor/ceiling, opponent.
  - Both tabs: search, position filter, scoring toggle (PPR/Half-PPR), sortable columns.
- **Trade Values** page: browses `in_season_trade_values` across all 5 live sources (Boone, CBS, FantasyPros, RSJ, USA Today).
- Visual system: "Turf Bright" palette (see `src/index.css` CSS custom properties), sidebar nav on desktop, hamburger/drawer on mobile.
- Not yet built (see `Fantasy Football/SITE_ROADMAP.md` at the repo root for the full plan): Home, Start/Sit, Player Comparison, Add/Drop, Trade Analyzer, Movers & Fallers, Expert Disagreement, Team Analyzer, Data Health.

## Quick start

```bash
npm install
npm run dev
```

Requires a `.env` (copy `.env.example`) with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` for the shared "Fantasy Football" Supabase project — **the whole app fails to render without these** (the pages barrel eagerly imports the Supabase client). Same variables must be set in the Vercel project's Environment Variables for production, since `.env` is gitignored and never ships.

## Build & test

```bash
npm run build   # tsc -b && vite build
npm test        # vitest run -- currently covers src/lib/blend.ts's pure calculation functions
npx tsc --noEmit
```

Deployed on Vercel, auto-deploys on push to `main`: https://nfl-fantasy-sigma.vercel.app

## Architecture notes

- `src/lib/blend.ts` — pure, unit-tested calculation functions (ROS value blending, weekly rank aggregation). No Supabase/React dependency; pages fetch rows and hand them to these functions.
- `src/lib/rosHistory.ts` — async Supabase helper for the previous week's ROS snapshot (used for "ROS Δ").
- `src/lib/consensusWeights.ts` — the source-weighting used for weekly rank aggregation, hand-copied from `Draft/config/settings.yaml`'s `consensus.weights` (not read live — if that file is retuned, update this one to match).
- `src/nav.ts` — single source of truth for site navigation (`NAV_ITEMS`), consumed by both `Sidebar` and `MobileNav`.

See `docs/DATA.md` for the Supabase schema this app reads and the blend/aggregation algorithms in detail.
