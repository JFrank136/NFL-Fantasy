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

## Draft Sharks ROS rankings (`src/sources/draftsharks_ros.py`)

`GET https://www.draftsharks.com/ros-rankings/load-rows` — public,
unauthenticated, same `tbody[data-player-row]` HTML-fragment shape as
weekly rankings, but a **different report**: rest-of-season rankings, not
one week's. Field names were verified live 2026-09-17 against the real
endpoint and match what's implemented, with one confirmed quirk: the
`games_played` cell's `data-value` renders as a float string (e.g.
`"16.0"`), not a plain int — `_to_int` in this module falls back to a
float parse to handle it.

**Query params**: same shape as weekly (`offset`, `limit`,
`pprSuperflexSlug`, `researchDepth=rankings`), but no `week` param (this
report isn't week-scoped), `fantasyPosition=""` returns **every** position
in one paginated pull (confirmed live: 429 QB/RB/WR/TE rows total — WR 171,
RB 111, TE 102, QB 45 — plus LB/DL/DB/K/DEF, which `fetch_draftsharks_ros`
filters out), `sort=-dsValue` (this report's default sort, unlike weekly's
`-weekly3dPts`).

**New `data-attribute` cells this report has that weekly doesn't**:
`rosWeeklyPts` (ROS points projection), `rosWeeklyFloorPts`,
`rosWeeklyCeilingPts`, `dsValue` (Draft Sharks' blended ROS trade value —
their "3D value" analog for this report), `games_played` (projected games
played rest of season — see the float-string quirk above),
`player.sipPlayerProfile.injury_prob` (injury risk — stored as raw text in
`RosRankingRow.injury_risk` rather than parsed, since its value format
wasn't fully characterized during implementation).

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

## Justin Boone trade values / ROS (`src/sources/boone_trade_values.py`)

No JSON API — scraped from Boone's Yahoo article pages
(`sports.yahoo.com/author/justin-boone/` lists his recent articles; a regex
over that page's `<a href>`s finds each position's trade-value-chart URL for
the target week, since article URLs aren't predictable/guessable).

**The URL slug changed for the 2026 season** — confirmed live 2026-09-17,
broke silently until then (every position looked "not yet published" because
the discovery regex just never matched anything):
- **Old** (2025 and earlier): `.../fantasy/article/fantasy-football-week-N-
  justin-boones-{qb,rb,wr,te}-trade-value-charts-{id}.html`
- **Current** (2026): `.../fantasy/article/2026-trade-value-charts--justin-
  boones-fantasy-football-{quarterback,running-back,wide-receiver,tight-end}-
  breakdown-for-week-N-{id}.html` — position is spelled out, not abbreviated,
  and the week number is its own token (`for-week-N-`) rather than a leading
  `week-N-` prefix.

If this "not yet published" state persists implausibly long for a position
Boone would obviously have posted, check the live author page's actual link
shape before assuming it's really unpublished — Yahoo has changed this slug
format at least once already with no warning.

## CBS / FantasyPros / RSJ trade values (added 2026-09-17)

Three more trade-value sources, captured for later accuracy analysis only —
**not wired into the site.** All three share `in_season_trade_values` /
`TradeValueRow` with Boone, distinguished by `source="cbs"|"fantasypros"|"rsj"`.
Each is confirmed server-rendered plain HTML (a real-user-agent
`requests.get` returns the full data table already in the response, no JS
needed) as of 2026-09-17.

**CBS Sports** (`src/sources/cbs_trade_values.py`) — one combined article per
week covering all 4 positions (`table.TableBuilder`, in QB/RB/WR/TE document
order). Slug isn't guessable (`.../dave-richards-week-N-trade-chart-and-...`,
wording varies), so the current week's URL is discovered from CBS's fantasy
news hub, `cbssports.com/fantasy/football/news/`, via a regex over its raw
HTML matching `week-N-trade-chart`. Each position table has 3 value columns;
only 2 are kept (label → stored as):
- RB/WR/TE header `[Player, tm, non, 0.5, PPR]` → keep `0.5` as `HALF` and
  `PPR` as `PPR`, drop `non`.
- QB header `[Player, tm, 1QB-4, 1QB-6, 2QB]` → keep `1QB-6` as `1QB` and
  `2QB` as `2QB`, drop `1QB-4` (QB values aren't PPR-sensitive; CBS instead
  varies them by passing-TD point value and 1QB/2QB league size).
No `Rk` column in the source — rank is derived from row order (rows are
pre-sorted by value descending).

**FantasyPros** (`src/sources/fantasypros_trade_values.py`) — one combined
article per week, 4 plain `<table>` tags (no class) in QB/RB/WR/TE order.
URL is `fantasypros.com/YYYY/MM/fantasy-football-trade-value-chart-week-N-YYYY/`
— predictable slug, unpredictable publish-date path — so the current week's
full URL is discovered from FantasyPros' own trade-value-chart hub page,
`fantasypros.com/content/nfl-trade-value-chart/`, via a regex over its raw
HTML. Header is `[Name, Team, Value, Change, ...]`; the single "Value"
column has **no stated scoring format** (no half/full-PPR split on the
page) — stored as-is under label `VALUE`, not guessed at. QB rows add a
"2QB Value" column (stored as `2QB`); TE rows add a "TEP Value" column
(tight-end-premium, stored as `TEP`); RB/WR have no second column
(`value_col2` is `None`, label `N/A`). Rank is derived from row order.

**Roto Street Journal (RSJ)** (`src/sources/rsj_trade_values.py`) — the one
source with genuinely separate URLs per position (unlike CBS/FantasyPros'
one-article-per-week). Built from "The Wolf of Roto Street"'s ROS rankings,
explicitly **full-PPR/1QB only** per the article text — no half-PPR variant
exists. URLs are unpredictable date-stamped paths
(`/YYYY/MM/DD/YYYY-fantasy-football-week-N-trade-value-chart[-position]/`),
discovered from RSJ's tag archive, `rotostreetjournal.com/tag/trade-value-chart/`.
**Slug quirk confirmed live**: the QB page has **no position suffix at
all**; RB/WR use singular `-chart-running-backs` / `-chart-wide-receivers`;
TE uses **plural** `-charts-tight-ends` (RSJ's own inconsistency, not a bug
here — the discovery regex matches both `chart` and `charts`). Each
position's table is a TablePress plugin table (`class="tablepress
tablepress-id-NNN"`, id varies per page — matched by the `tablepress`
prefix, not the full class) with an explicit `[Rank, Player Name, Team,
Value]` header — rank comes straight from the source, no derivation needed.
Single value column, stored under label `PPR`; `value_col2` is always
`None`, label `N/A`.

**USA Today** (`src/sources/usatoday_trade_values.py`) — one combined article
per week covering QB/RB/WR/TE. The current week's URL is discovered from
USA Today's fantasy-football hub:

`https://www.usatoday.com/sports/fantasy/football/`

The hub links the current article under the `fantasy.usatoday.com` hostname.
A normal `requests.get` using the browser-style User-Agent used by this source
returns the server-rendered HTML tables directly; no JavaScript execution or
cookies are required.

The article contains four position sections identified by their `<h2>`
headings (`Quarterback trade value chart`, `Running back trade value chart`,
etc.), with the following confirmed column shapes:

- QB: `[RK, Player, 1QB, 6/TD, SFLEX]`
  - `1QB` is used for both stored value columns (`HALF` and `FULL`) because
    the QB value is not PPR-sensitive.
- RB: `[RK, Player, STD, Half, PPR]`
  - `Half` -> `HALF`
  - `PPR` -> `FULL`
- WR: `[RK, Player, STD, Half, Full]`
  - `Half` -> `HALF`
  - `Full` -> `FULL`
- TE: `[RK, Player, STD, Half, Full]`
  - `Half` -> `HALF`
  - `Full` -> `FULL`

The parser validates each requested table's exact expected headers and raises
a fetch/parse error if a requested table is missing, its headers change, or a
numeric value cannot be parsed. This is deliberate so a source-side layout
change fails loudly instead of silently writing incomplete data.

`pull_usatoday_trade_values.py` follows the same combined-article flow as CBS
and FantasyPros: discover article URL -> fetch/parse -> normalize -> validate
-> raw snapshot -> append to `trade_values_long.csv` -> write
`data/last_usatoday_trade_values_status.json`.

Confirmed live 2026-09-17 for Week 2:
QB 36 rows, RB 75 rows, WR 90 rows, TE 37 rows.

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
truth, Supabase is a secondary copy. Four tables — the three ranking/value
tables are append-only for the same reason the local CSVs are: a new
`pulled_at` for the same logical row is a new row, never an overwrite, so
re-pulling a not-yet-played week to catch DraftSharks' mid-week updates
preserves the full history Jared asked for. The fourth (`in_season_pull_status`)
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
- **`in_season_ros_rankings`** — mirrors `RosRankingRow`: `season, source,
  scoring, pulled_at, as_of_week, source_player_id, player_name,
  canonical_name, team, position, rank, tier_overall, tier_positional,
  projection, floor_proj, ceiling_proj, ds_value, strength_of_schedule,
  games_played, injury_risk, bye`, plus `id` and `created_at`. Indexed on
  `(season, source, scoring, canonical_name)`. `as_of_week` is a snapshot
  marker only, not part of the latest-view's key (see below) — ROS
  rankings describe the rest of the season, not one specific week.
- **`in_season_pull_status`** — one row per `dataset` (primary key, not
  append-only): `last_success_at, last_attempt_at, status, message,
  row_count`. Lets a consumer (or a human) check whether a pull is stale
  without scanning the append-only tables.

Three views, each `select distinct on (...) ... order by ..., pulled_at desc`
over their base table — i.e. "latest pull per logical key" without the
caller having to write that query themselves: `in_season_rankings_latest`
(keyed on `season, week, source, scoring, canonical_name`),
`in_season_trade_values_latest` (keyed on `season, week, source, position,
canonical_name`), and `in_season_ros_rankings_latest` (keyed on `season,
source, scoring, canonical_name` — deliberately **without** `as_of_week`,
unlike the other two views' `week`, since "latest" for a ROS row means the
most recent snapshot regardless of which week it was captured in).

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
