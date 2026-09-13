# In-Season Site — Shared Foundation Design

Date: 2026-09-12
Scope: Step 1 of `SITE_ROADMAP.md`'s "Suggested Implementation Order" — the
Supabase data layer and shared player identity system that every later page
(Start/Sit, Trade Analyzer, Movers & Fallers, etc.) will build on. No page
logic, shared calculations, or UI components are built in this pass — see
"Out of scope" below.

## Context

- The `in-season/` pipeline currently pulls Draft Sharks / Boone / Smythe
  weekly rankings and Boone's ROS trade values into local files only
  (`data/processed/rankings_long.csv`, `data/processed/trade_values_long.csv`)
  — Supabase was deliberately deferred until the schema proved out over a
  few real weeks. That trial period is over; this design is the migration.
- Vampire (`Vampire/matchup-tool`) and BigBallerLeague already share one
  Supabase project ("Fantasy Football", `tdtchffawcmkvgrccjza`). This design
  reuses that same project rather than creating a new one.
- `in-season/team-analyzer` is an existing but essentially unused
  Vite+React+TS+Tailwind scaffold with stub pages and stale
  DraftSharks-login scraper env vars. Per the roadmap ("rebuild the existing
  Team Analyzer rather than build a separate Roster Analyzer") and Jared's
  confirmation, this scaffold becomes the root of the new consolidated site.
- Player name matching today is duplicated per-consumer: `Draft/src/matching.py`
  (Python) and Vampire's `src/name-matching.js` each independently read
  `Draft/data/aliases.csv` and implement their own normalize+lookup. Known
  gap: some players (e.g. Skattebo, Gainwell) fall through matching silently
  today with no visibility when it happens.

## 1. Supabase schema

New tables in the existing "Fantasy Football" Supabase project, prefixed
`in_season_` to match the project's existing `vampire_` naming convention.

### `in_season_rankings`

Long format, one row per pull. Mirrors `RankingRow` in
`in-season/src/schema.py` plus a new `canonical_name` column (see Player
Identity below).

| column | type | notes |
|---|---|---|
| `id` | bigserial PK | |
| `season` | int | |
| `week` | int | |
| `source` | text | `draftsharks` \| `boone` \| `smythe` |
| `scoring` | text | `half-ppr` \| `ppr` |
| `pulled_at` | timestamptz | UTC |
| `source_player_id` | text | |
| `player_name` | text | raw name as pulled |
| `canonical_name` | text | resolved via `player_identity.py` |
| `team` | text \| null | |
| `position` | text | |
| `rank` | int \| null | |
| `projection` | float \| null | |
| `floor_proj` | float \| null | |
| `ceiling_proj` | float \| null | |
| `tier` | int \| null | |
| `bye` | int \| null | |
| `opponent` | text \| null | |
| `created_at` | timestamptz default now() | insert time, distinct from `pulled_at` (source's own timestamp) |

**Append-only.** No natural-key uniqueness constraint is enforced — a
re-pull of an already-pulled week is a new row with a new `pulled_at`,
never an update, matching the existing local-CSV behavior (Draft Sharks
revises a week's numbers multiple times before kickoff and every version
is kept). Index on `(season, week, source, scoring, canonical_name)` for
lookup performance.

No pruning/retention policy — data volume is trivial (~260k rows/season for
rankings, tens of MB) and Jared wants full multi-season history preserved
for end-of-season model tuning.

### `in_season_trade_values`

Mirrors `TradeValueRow` in `in-season/src/schema.py` plus `canonical_name`.

| column | type | notes |
|---|---|---|
| `id` | bigserial PK | |
| `season` | int | |
| `week` | int | week the chart was published for |
| `source` | text | `boone` today, room for more later |
| `position` | text | |
| `pulled_at` | timestamptz | |
| `source_url` | text | |
| `rank` | int \| null | |
| `player_name` | text | |
| `canonical_name` | text | |
| `team` | text \| null | always null today (not present in source) |
| `value_col1_label` | text | e.g. `HALF` or `1QB` |
| `value_col1` | float \| null | |
| `value_col2_label` | text | e.g. `PPR` or `2QB` |
| `value_col2` | float \| null | |
| `created_at` | timestamptz default now() | |

Same append-only, no-pruning treatment as `in_season_rankings`.

### `in_season_pull_status`

One row per dataset, **upserted** (current state, not history) — a direct
mirror of what `data/last_run_status.json` and
`data/last_trade_values_status.json` already track locally, so a future
Data Health page can read freshness/validation state from Supabase without
touching local files.

| column | type | notes |
|---|---|---|
| `dataset` | text PK | e.g. `draftsharks/half-ppr`, `boone_trade_values` |
| `last_success_at` | timestamptz \| null | |
| `last_attempt_at` | timestamptz | |
| `status` | text | `healthy` \| `warning` \| `failed` |
| `message` | text \| null | validation/failure detail |
| `row_count` | int \| null | rows in the most recent successful pull |

### Latest-value views

- `in_season_rankings_latest` — `DISTINCT ON (season, week, source, scoring, canonical_name)` ordered by `pulled_at DESC`.
- `in_season_trade_values_latest` — `DISTINCT ON (season, week, source, position, canonical_name)` ordered by `pulled_at DESC`.

These satisfy the roadmap's "Define queries/helpers for current/latest
values" item without requiring page-level code to re-derive "latest" logic
each time.

### Access pattern

Matches Vampire exactly: RLS off on all three tables (same low-stakes,
no-login tradeoff already accepted for `vampire_*`). Anon key is used for
read-only browser access from the site; the service-role key is used only
server-side, in the new push script below, and is never shipped to the
browser.

## 2. Push automation

New `in-season/scripts/push_to_supabase.py`:

- Reads the freshly-written rows from the current pull run (not the whole
  CSV history each time — only what the current `pull_week.py` /
  `pull_trade_values.py` invocation just produced) and inserts them into
  `in_season_rankings` / `in_season_trade_values`.
- Upserts `in_season_pull_status` from the same status info already written
  to `data/last_run_status.json` / `data/last_trade_values_status.json`.
- Uses `SUPABASE_SERVICE_ROLE_KEY` from environment (same pattern as
  Vampire's `.env`).

`in-season/scripts/scheduled_pull.ps1` gets a new step calling this script
after each successful rankings/trade-value pull. **A Supabase push failure
does not fail the overall scheduled run or trigger the "we lost this week"
failure email** — the local CSV already has the data safely (nothing is
lost), so a push failure is logged and mentioned in the existing
success/warning email as a "Supabase sync pending" note, not treated as a
data-loss event.

One-time backfill script (`scripts/backfill_supabase.py` or a `--backfill`
flag on `push_to_supabase.py`): runs `player_identity.py` over the full
existing local CSV history (since 2026-09-08) and pushes it to Supabase
once, so the initial load has `canonical_name` resolved on historical rows
too, not just rows pulled going forward.

## 3. Player identity

New `in-season/src/player_identity.py`:

- `normalize_name(raw_name: str) -> str` — same tiny algorithm as
  `Draft/src/matching.py` (lowercase, strip `.`/`'`/`-`, drop generational
  suffixes). Not imported cross-project (Draft and in-season aren't set up
  as installable packages of each other) — reimplemented at this same small
  scale, consistent with Vampire's JS already doing the same independently
  against the same source file.
- `load_aliases() -> dict[tuple[str, str, str], str]` — reads
  `Draft/data/aliases.csv` directly (read-only; the shared source-of-truth
  file, not a new copy of the data).
- `canonical_name_for(raw_name: str, raw_team: str | None, source: str) -> str`
  — looks up the alias table by `(normalized_name, normalized_team, source)`;
  falls back to the bare normalized name if no alias entry exists.

**Applied once, centrally**, when `RankingRow` / `TradeValueRow` instances
are built in the pull scripts — both dataclasses in `in-season/src/schema.py`
gain a `canonical_name: str` field, flowing through to CSV output and the
Supabase push. No page or later shared-calculation code needs its own name
matching (satisfies the roadmap's "avoid page-specific name-matching logic").

**Visibility for unmatched names:** every fallback-to-normalized-name case
(no alias hit) is appended to `data/unmatched_names.log` with the raw name,
team, source, and week, and summarized in the run's existing summary output.
This does not fix the underlying Skattebo/Gainwell-style matching gaps —
that requires broader alias-table maintenance or fuzzy matching, out of
scope here — but it makes gaps visible immediately instead of silently
producing a slightly-wrong blended value somewhere downstream.

## 4. Scaffold prep (new site root)

- Rename `in-season/team-analyzer` → `in-season/site` (it's about to become
  the whole consolidated site, not just Team Analyzer — keeping the old name
  would be misleading).
- Strip the stale `DRAFTSHARKS_EMAIL`/`DRAFTSHARKS_PASSWORD` scaffold env
  vars and any dependent scraper-login code — the roadmap explicitly calls
  for removing dependence on the old separate scrapers in favor of the
  `in-season` pipeline.
- `git init` `in-season/` as its own repo (it already has a `.gitignore`
  but was never initialized) — matches the existing per-tool repo pattern
  (`Draft/`, `Vampire/matchup-tool/` each have their own `.git`). The
  renamed `site/` subfolder ships as part of this same repo, not a separate
  one, since it's tightly coupled to the pipeline that feeds it.
- Push to a new GitHub repo; connect Vercel to it for hosting, with the
  Vercel project root set to `in-season/site`. Supabase anon key set as a
  Vercel environment variable (`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`),
  not hardcoded into a template file.

No stub page content (`Players.tsx`, `Trends.tsx`, etc.) is built out in
this pass — they stay as placeholders until each page's own
brainstorm/design/implementation cycle.

## Out of scope for this design

Deferred to later, page-specific design passes, per YAGNI and the roadmap's
own suggested order:

- Standalone `players` registry table (decided against — canonical identity
  is resolved at ingestion time instead, see above).
- Shared calculations (blended ROS value, aggregate weekly rank, movement,
  disagreement) — built alongside the first page that actually needs them.
- Reusable UI components (player selector, comparison table, confidence
  indicator, etc.) — no frontend page work happens in this pass.
- Global context (current NFL week, scoring setting, freshness state as
  *app* state, not just Supabase data) — built when the first page needs to
  consume it.
- Fixing the underlying Skattebo/Gainwell-style name-matching gaps beyond
  making them visible via the unmatched-names log.
