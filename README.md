# In-Season Tools

Weekly fantasy football data pipeline (Draft Sharks, Justin Boone, and Joel
Smyth, with more sources likely to be added over time) feeding a set of
in-season tools: start/sit, trade, waiver wire, rest-of-season, and whatever
else comes later.

## Why this exists separately from `Draft/`

`Draft/` builds the one-time preseason draft board. This project pulls **weekly**
rankings/projections throughout the season and keeps every week's pull instead of
overwriting it, since a week's rankings get updated multiple times before kickoff
and Jared wants the history preserved, not just the latest snapshot.

## Sources (see `docs/DATA.md` for verified request/response shapes)

- **Draft Sharks weekly rankings** — public, unauthenticated `load-rows` endpoint.
  No login needed (unlike `Draft/`'s draft-day CSV export, which does require one).
- **Justin Boone (via Yahoo)** — pulled via Yahoo's own public, unauthenticated
  `api/fanPro/` endpoint (`src/sources/yahoo_weekly_consensus.py`), the same
  endpoint `Draft/src/sources/yahoo_consensus.py` uses for the draft-day
  board, extended here with a `week` param. Experts are resolved by name from
  the response's own `expertNames` map, not a hardcoded id.
- **Joel Smyth** — same Yahoo `fanPro` mechanism as Boone (`src/sources/yahoo_weekly_consensus.py`,
  expert resolved by name, not a hardcoded id). Confirmed live as a normal
  weekly-rankings source alongside Boone. Like Boone, Smyth typically hasn't
  posted a given week's rankings until Thursday — a pull attempted before then
  returns zero rows, which `validate.py`'s `check_nonempty` flags as a
  validation failure (`"Pull returned zero rows."`) rather than a true scrape
  break; `scripts/scheduled_pull.ps1`'s status email treats that specific
  message as "not yet published," distinct from a real failure.
- **Matt Harmon, Scott Pianowski, Hayden Winks** (added 2026-09-18) — the other
  three Yahoo analysts, same mechanism and same weekly pull (sources `harmon`,
  `pianowski`, `winks`). **Archival only**: they land in `in_season_rankings`
  so the full-season history exists, but the site deliberately ignores them
  (`site/src/lib/useWeeklyRows.ts` filters to draftsharks/boone/smythe) until
  they're wired into the blend. Verified live for week 2: ~260–310 rows each.
- **Justin Boone rest-of-season trade values** — scraped directly from
  Boone's Yahoo article pages since there's no JSON API for this data.
  Article URLs aren't predictable/guessable week to week, so
  `src/sources/boone_trade_values.py` discovers each week's 4 position URLs
  from Boone's author page (`sports.yahoo.com/author/justin-boone/`) before
  scraping them — see `docs/DATA.md` for the exact URL slug format, which
  Yahoo has already changed once (2026-09-17) with no warning. Stored
  separately from weekly rankings — `data/processed/trade_values_long.csv`,
  its own schema (`TradeValueRow`) — since the data shape (rank + two
  source-labeled value columns, e.g. HALF/PPR for RB/WR/TE but 1QB/2QB for
  QB) doesn't fit `RankingRow`.
- **Draft Sharks rest-of-season (ROS) rankings** — a separate report from
  weekly rankings (`ros-rankings/load-rows`, still public/unauthenticated),
  carrying Draft Sharks' own blended ROS trade value (`ds_value`) plus
  ROS floor/ceiling projections, strength of schedule, games-played, and
  injury risk. Pulled all-positions-in-one-call per scoring format (unlike
  weekly, which is one call per position) — see
  `src/sources/draftsharks_ros.py`. Stored separately from both weekly
  rankings and Boone's trade values, in its own `in_season_ros_rankings`
  table, since neither existing shape fits: it needs floor/ceiling/SOS
  columns weekly's trade-value table doesn't have, and it isn't a
  per-week-published report the way weekly rankings are.
- **CBS Sports (Dave Richard), FantasyPros, and Roto Street Journal (RSJ)
  trade values** — three more trade-value sources added 2026-09-17, wired
  into the site's Trade Values page as of 2026-09-18 alongside Boone.
  Each appends `source="cbs"|"fantasypros"|"rsj"` rows to the same
  `trade_values_long.csv` / `in_season_trade_values` table Boone uses — no
  schema change needed, since `TradeValueRow`'s two-value-column shape fits
  all of them once each is trimmed to its two most useful columns (CBS:
  half-PPR/full-PPR, or 1QB/2QB for QB, dropping its third non-PPR/4pt
  column; FantasyPros: its single blended "Value" plus a 2QB/TEP variant
  where published; RSJ: full-PPR only, no second column). None of their
  article URLs are predictable ahead of time, so each source module
  (`src/sources/cbs_trade_values.py`, `fantasypros_trade_values.py`,
  `rsj_trade_values.py`) discovers the current week's URL(s) from a stable
  hub/archive page first, the same pattern Boone's module established — see
  `docs/DATA.md` for each hub URL and exact table shape.
- **USA Today trade values** — retired 2026-10-07: usatoday.com now requires a
  TollBit token for automated access (402 "Access Restricted"). The code is
  archived in `legacy/usatoday/` and no longer runs in the scheduled pull;
  historical `source="usatoday"` rows remain in the data.

## Storage

Two layers, both populated on every pull:

- **Local files** — `data/raw/` (immutable timestamped snapshots) and
  `data/processed/rankings_long.csv` / `trade_values_long.csv` (append-only,
  standardized long format). This remains the source of truth and audit trail.
- **Supabase** ("Fantasy Football" project, `tdtchffawcmkvgrccjza` — same
  project Vampire and BigBallerLeague use) — `in_season_rankings`,
  `in_season_trade_values`, `in_season_ros_rankings`, `in_season_pull_status`
  tables, pushed incrementally by `scripts/push_to_supabase.py` (wired into
  `scripts/scheduled_pull.ps1`, runs after every pull). A push failure doesn't
  fail the scheduled run or lose data — the local CSV already has it, and the
  next run retries from a persisted watermark
  (`data/supabase_push_state.json`). See `docs/DATA.md` for the exact schema.

## Scheduled runs & notifications

`scripts/scheduled_pull.ps1` is the Windows Task Scheduler entry point — runs
`pull_week.py`, `pull_trade_values.py`, `pull_draftsharks_ros.py`, the
Supabase push, and the Vampire weekly-projection refresh, with a
network-readiness wait for wake-from-sleep races. **Gotcha**: this script
lives under OneDrive, so a same-morning edit can lose the race against
OneDrive's own sync-down if Task Scheduler fires right after — the task can
end up running the pre-edit version with no error, just a step silently
missing from that run's log. It emails Jared an HTML status summary via
Gmail SMTP (credential at `%LOCALAPPDATA%\FantasyInSeasonPull\gmail_cred.xml`)
built from `data/last_run_status.json` / `data/last_trade_values_status.json`
/ `data/last_draftsharks_ros_status.json`, one section per scoring format,
each split into a **Weekly** subsection (sources from `pull_week.py`) and a
**ROS** subsection (Draft Sharks ROS Rankings + Boone ROS together). Sources
are discovered dynamically from each status JSON's own keys rather than
hardcoded, so a new source shows up with no changes to the email script.
Each row distinguishes three states — ok, not yet published (Boone/Smyth
pre-Thursday), and a real failure — rather than collapsing "not published
yet" into a false failure alarm. The "weeks captured" note per source is
capped to current + next week (not every week Draft Sharks has ever pulled)
since Draft Sharks intentionally pulls the whole rest of the season on every
run.

## Name matching

`src/player_identity.py` resolves a `canonical_name` for every row at
ingestion, reading `Draft/data/aliases.csv` directly (same file Vampire's
`name-matching.js` already reads independently — read it, don't fork a copy
of the data). **Gotcha**: that file's `source` column (`yahoo`,
`footballguys`) is the site that spelled a name a certain way, not a
fantasy-analyst source — none of this project's own sources (`draftsharks`,
`boone`, `smythe`) ever appear there, so matching ignores source/team
entirely and keys on normalized name alone (both straight and curly
apostrophes since 2026-09-18). The Draft Sharks → Vampire
weekly-projection handoff (see `../Vampire/matchup-tool/scripts/refresh-weekly-projection.js`)
still reuses Vampire's own separate `normalizeName` for its own matching —
the two aren't unified, just both reading the same source CSV.

**Gotcha — `canonical_name` isn't a safe join key on its own**: two
different real people can share a name (confirmed: a WR and an LB both
named Justin Jefferson). Any code joining/grouping rows across sources must
key on `(canonical_name, normalized_position)`, not name alone — see
`docs/DATA.md`'s Supabase-shape section and `normalizePosition`/`identityKey`
in `site/src/lib/blend.ts` for the established pattern.

## Site (`site/`)

A Vite+React+TS+Tailwind app — the future home of the roadmap's consolidated
tools (Start/Sit, Trade Analyzer, etc., see `../SITE_ROADMAP.md` at the repo
root above this one). Deployed via Vercel from
`https://github.com/JFrank136/NFL-Fantasy.git`, live at
`https://nfl-fantasy-sigma.vercel.app`. Two real pages are live against
Supabase as of 2026-09-18:

- **Rankings** (`site/src/pages/Rankings.tsx`) — Weekly (default tab,
  auto-sorted by a DS/Boone/Smyth blended "Agg. Rank", QB/RB/WR/TE position
  filter only — no K/DST) and ROS (Draft Sharks + Boone blended value,
  cross-position overall rank, `ALL` position option retained since that
  rank genuinely is cross-position). Pure blending logic lives in
  `site/src/lib/blend.ts`, tested in `blend.test.ts`.
- **Trade Values** (`site/src/pages/TradeValues.tsx`) — pivots all 5 trade-value
  sources plus Draft Sharks' ROS `ds_value` ("DS 3D") into one row per player with a normalized cross-source score, a
  PPR/Half-PPR toggle, and per-source column show/hide. Pure logic in
  `site/src/lib/tradeValues.ts`, tested in `tradeValues.test.ts` — see
  `docs/DATA.md`'s "Site: Trade Values page" section for the label-parsing
  convention it uses.

## Usage

```bash
pip install -r requirements.txt
python scripts/pull_week.py --week 1 --source draftsharks --scoring half-ppr,ppr
python scripts/pull_trade_values.py --week 1
```

See `scripts/pull_week.py --help` for all options. Every run prints a summary
(rows pulled, validation warnings/failures, output paths) and exits non-zero on
a validation failure — treat that as "this week needs attention," not a soft
warning to skim past.
