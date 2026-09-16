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
- **Justin Boone rest-of-season trade values** — scraped directly from
  Boone's Yahoo article pages (`fantasy-football-week-N-justin-boones-{pos}-trade-value-charts`)
  since there's no JSON API for this data. Article URLs aren't
  predictable/guessable week to week, so `src/sources/boone_trade_values.py`
  discovers each week's 4 position URLs from Boone's author page
  (`sports.yahoo.com/author/justin-boone/`) before scraping them. Stored
  separately from weekly rankings — `data/processed/trade_values_long.csv`,
  its own schema (`TradeValueRow`) — since the data shape (rank + two
  source-labeled value columns, e.g. HALF/PPR for RB/WR/TE but 1QB/2QB for
  QB) doesn't fit `RankingRow`.

## Storage

Two layers, both populated on every pull:

- **Local files** — `data/raw/` (immutable timestamped snapshots) and
  `data/processed/rankings_long.csv` / `trade_values_long.csv` (append-only,
  standardized long format). This remains the source of truth and audit trail.
- **Supabase** ("Fantasy Football" project, `tdtchffawcmkvgrccjza` — same
  project Vampire and BigBallerLeague use) — `in_season_rankings`,
  `in_season_trade_values`, `in_season_pull_status` tables, pushed
  incrementally by `scripts/push_to_supabase.py` (wired into
  `scripts/scheduled_pull.ps1`, runs after every pull). A push failure doesn't
  fail the scheduled run or lose data — the local CSV already has it, and the
  next run retries from a persisted watermark
  (`data/supabase_push_state.json`). See `docs/DATA.md` for the exact schema.

## Scheduled runs & notifications

`scripts/scheduled_pull.ps1` is the Windows Task Scheduler entry point — runs
`pull_week.py`, `pull_trade_values.py`, the Supabase push, and the Vampire
weekly-projection refresh, with a network-readiness wait for wake-from-sleep
races. It emails Jared an HTML status summary via Gmail SMTP (credential at
`%LOCALAPPDATA%\FantasyInSeasonPull\gmail_cred.xml`) built from
`data/last_run_status.json` / `data/last_trade_values_status.json`, one
section per scoring format, one row per source. Sources are discovered
dynamically from the status JSON's own keys rather than hardcoded, so a new
source added to `pull_week.py`'s `ALL_SOURCES` shows up with no changes to
the email script. Each row distinguishes three states — ok, not yet
published (Boone/Smyth pre-Thursday), and a real failure — rather than
collapsing "not published yet" into a false failure alarm.

## Name matching

`src/player_identity.py` resolves a `canonical_name` for every row at
ingestion, reading `Draft/data/aliases.csv` directly (same file Vampire's
`name-matching.js` already reads independently — read it, don't fork a copy
of the data). **Gotcha**: that file's `source` column (`yahoo`,
`footballguys`) is the site that spelled a name a certain way, not a
fantasy-analyst source — none of this project's own sources (`draftsharks`,
`boone`, `smythe`) ever appear there, so matching ignores source/team
entirely and keys on normalized name alone. The Draft Sharks → Vampire
weekly-projection handoff (see `../Vampire/matchup-tool/scripts/refresh-weekly-projection.js`)
still reuses Vampire's own separate `normalizeName` for its own matching —
the two aren't unified, just both reading the same source CSV.

## Site (`site/`)

A Vite+React+TS+Tailwind app — the future home of the roadmap's consolidated
tools (Start/Sit, Trade Analyzer, etc., see `../SITE_ROADMAP.md` at the repo
root above this one). Deployed via Vercel from
`https://github.com/JFrank136/NFL-Fantasy.git`, live at
`https://nfl-fantasy-sigma.vercel.app`. `site/src/lib/supabase.ts` has a
working Supabase client (verified against the live project) but **no page
queries it yet** — the current tabs still render pre-Supabase placeholder
components. Building real pages against `in_season_rankings_latest` /
`in_season_trade_values_latest` is the next work here.

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
