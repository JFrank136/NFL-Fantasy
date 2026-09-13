# Data sources — verified request/response shapes

Verified live 2026-09-08. This doc exists so a future session doesn't have to
re-derive these by trial and error against the live sites (same purpose as
`Draft/docs/DATA.md`, which this project deliberately mirrors the style of).

## Draft Sharks weekly rankings (`src/sources/draftsharks_weekly.py`)

`GET https://www.draftsharks.com/weekly-rankings/load-rows` — **public,
unauthenticated**, confirmed via plain `curl`/`requests` with no cookies or
session. This is a different endpoint from `Draft/`'s draft-day CSV export
(`Draft/src/sources/draftsharks.py`), which does require a logged-in Playwright
session — the weekly in-season page needs none of that.

**Query params**: `offset` (int, paginate), `limit` (int, page size — the site's
own JS uses 225 then no limit for the remainder; 300 in one call works fine),
`fantasyPosition` (blank = all positions), `pprSuperflexSlug` (`ppr` / `half-ppr`
confirmed; `non-ppr`/`superflex`/`tep` appear as toggle options on the page but
are **unverified** against this endpoint — check the response before trusting
them), `sort` (`-weekly3dPts` matches the page's default sort), `week` (1-18),
`researchDepth=rankings`.

**Response**: not JSON — a raw HTML fragment, one `<tbody data-player-row ...>`
block per player, meant to be appended into the page's table. Paginate by
increasing `offset` until a call returns zero `data-player-row` blocks.

Per-`<tbody>` attributes (all on the `<tbody>` tag itself):
`data-key` (Draft Sharks' internal player id — stable, use as `source_player_id`),
`data-player-name`, `data-fantasy-position`, `data-team-id` (numeric — the
human-readable team code is in the nested `<img class="team-badge" src="/img/icons/teams/{TEAM}.svg">`,
not this attribute), `data-tier-overall`, `data-tier-positional`, `data-is-rookie`.

Per-cell (`<td data-attribute="..." data-value="...">`) — `data-value` is the
plain-text number/string, already what you want:
`matchup` (e.g. `"@KC"` or `"NO"`), `strength_of_schedule` (e.g. `"-13.3%"`),
`player.team.bye`, `weeklyFloorPts`, `consensus_projection`, `weeklyPts`
("DS Proj" on the page — Draft Sharks' own single-model projection, distinct
from `weekly3dPts`), `weeklyCeilingPts`, `weekly3dPts` ("3D Proj" — Draft
Sharks' blended/composite projection; **this is what `Draft/`'s draft-day board
uses as its primary "3D Value" metric**, so treat it as the primary weekly
number here too, not `weeklyPts`). The row's overall rank (position across all
positions combined, since the page sorts by `-weekly3dPts`) is in the first
`<td>`, a bare `<span>{N}</span>` inside `.rank-index`.

**Known real-data quirk**: a bye-week player appears in the list with **no**
`matchup`/opponent value (empty `data-value=""`) rather than being omitted —
don't treat a blank matchup as a parse failure, it's a real "not playing this
week" signal worth keeping.

## Justin Boone (`src/sources/boone_weekly.py`)

Not scraped from Yahoo's article HTML directly — Yahoo's rankings tables are
either bot-protection-gated (a plain HTTP fetch of the article returns an
anti-bot challenge page, confirmed via `curl`) or, for a numbered ranking table,
rendered via an embedded FantasyPros partner widget (`<iframe src="https://partners.fantasypros.com/external/widget/fp-widget.php?...">`).
That widget itself just loads a placeholder `<div>`; the real data comes from a
second request the widget's own JS makes, which is what this project calls
directly:

`GET https://partners.fantasypros.com/api/v1/consensus-rankings.php` — public,
unauthenticated, plain JSON (no JSONP wrapper needed if `callback` is omitted
from the query string).

**Query params**: `sport=NFL`, `position` (one of `QB`/`RB`/`WR`/`TE`/`DST`/`K`
— **one call per position**, this endpoint does not return all positions at
once), `year`, `week`, `id=1663` (Boone's FantasyPros expert id — confirmed
live), `type=ST`, `scoring` (`HALF` or `PPR` — confirmed both work; don't pass
anything else, unrecognized values silently fall back to an unpredictable
default per the same pattern `Draft/docs/DATA.md` documents for the Yahoo
consensus endpoint), `filters=317`, `widget=ST`.

**Response shape**:
```json
{
  "position_id": "RB", "scoring": "HALF", "week": "1", "count": 50,
  "players": [
    {"player_id": 22968, "player_name": "Jahmyr Gibbs", "player_team_id": "DET",
     "player_position_id": "RB", "player_bye_week": "6", "player_opponent": "vs. NO",
     "rank_ecr": 1, "pos_rank": "RB1", "r2p_pts": "21.8", "start_sit_grade": "A+"}
  ]
}
```
`r2p_pts` is the projection ("points to reach" — the field name FantasyPros
uses across its site). `rank_ecr` here is Boone's own rank for this single-expert
pull (this endpoint is single-expert when `id` is given), not a consensus rank.

## Joel Smyth (`src/sources/smythe_weekly.py`) — UNCONFIRMED for weekly

Assumed to use the identical FantasyPros endpoint above with `id=7604` (the ID
`Draft/src/sources/yahoo_consensus.py` already resolved **by name** from
Yahoo's draft-day consensus endpoint's `expertNames` map — not a guess, but
also not yet independently confirmed for the *weekly* endpoint specifically).

**Confirmed 2026-09-08**: the Yahoo article link initially checked for Smyth
(`2026-fantasy-football-rankings-ppr-joel-smyth-193959938.html`) is his
**preseason overall board**, not a weekly numbered ranking — no `week` param,
no FantasyPros iframe on the page at all (the table renders as static content
directly in the article). Per Jared, that page's own text says PPR rankings
"come Thursday" — so a true weekly Smyth ranking may exist starting later in
Week 1 at a similar URL, or may only ever be this single preseason-style board
even once "updated." **Confirm against a real Smyth-authored weekly article
before trusting `id=7604` for weekly pulls.**

**Until confirmed**: `id=7604` against the weekly endpoint returned data, but
its top-8 RBs were byte-identical to Boone's (`id=1663`) pull for the same
week/scoring — inconclusive (could be genuine top-of-position consensus, could
be a silent fallback to a default expert). `validate.py`'s
`check_not_identical_to_other_source` exists specifically to catch this: it
flags — does not silently drop — a Smyth pull whose player order matches
Boone's beyond a small overlap threshold, so a human looks at it rather than
the pipeline trusting bad data by default.

## Supabase shape (`supabase/migrations/0001_in_season_foundation.sql`)

Live in the "Fantasy Football" Supabase project (`tdtchffawcmkvgrccjza` — same
project Vampire and BigBallerLeague use). Pushed incrementally after every
pull by `scripts/push_to_supabase.py`; local files remain the source of
truth, Supabase is a secondary copy. Three tables — the two ranking/value
tables are append-only for the same reason the local CSVs are: a new
`pulled_at` for the same logical row is a new row, never an overwrite, so
re-pulling a not-yet-played week to catch DraftSharks' mid-week updates
preserves the full history Jared asked for. The third (`in_season_pull_status`)
is a small mutable status table, one row per dataset:

- **`in_season_rankings`** — `season, week, source, scoring, pulled_at,
  source_player_id, player_name, canonical_name, team, position, rank,
  projection, floor_proj, ceiling_proj, tier, bye, opponent`, plus `id`
  (bigserial PK) and `created_at`. Indexed on
  `(season, week, source, scoring, canonical_name)`.
- **`in_season_trade_values`** — mirrors `TradeValueRow`: `season, week,
  source, position, pulled_at, source_url, rank, player_name,
  canonical_name, team, value_col1_label, value_col1, value_col2_label,
  value_col2`, plus `id` and `created_at`. Indexed on
  `(season, week, source, position, canonical_name)`.
- **`in_season_pull_status`** — one row per `dataset` (primary key, not
  append-only): `last_success_at, last_attempt_at, status, message,
  row_count`. Lets a consumer (or a human) check whether a pull is stale
  without scanning the append-only tables.

Two views, both `select distinct on (...) ... order by ..., pulled_at desc`
over their base table — i.e. "latest pull per logical key" without the
caller having to write that query themselves: `in_season_rankings_latest`
(keyed on `season, week, source, scoring, canonical_name`) and
`in_season_trade_values_latest` (keyed on `season, week, source, position,
canonical_name`).

**`canonical_name` on every row**: resolved via `src/player_identity.py`
from `Draft/data/aliases.csv` (the same alias file `Draft/src/matching.py`
and Vampire's `name-matching.js` already read). That file is keyed by
`(raw_name, raw_team, source)` where `source` means the *site* a name was
scraped from ("yahoo", "footballguys") — none of in-season's own sources
(`draftsharks`, `boone`, `smythe`) ever appear in that column, so lookups
here deliberately ignore `source`/`team` and match on normalized name only
(punctuation/case/suffix-stripped). The file is small and curated
(~20 rows), so name-only collisions aren't a practical risk — but this does
**not** solve cross-dataset gaps like a player missing entirely from one
source's pull; see `docs/superpowers/specs/2026-09-12-supabase-foundation-design.md`
for what's explicitly out of scope.
