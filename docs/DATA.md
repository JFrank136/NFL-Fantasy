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

**Rank scale gotcha — confirmed live 2026-09-19 (week 2).** This rank is Draft Sharks' OVERALL rank
across everything the endpoint returns, IDP/K/DEF included, not a rank within the player's position
group: week-2 RB ranks spanned 3-836, WR 10-870 and QB 1-820, while Boone/Smyth (Yahoo `FLX` / `QB`
queries) ran 1-~155 (RB/WR/TE) and 1-32 (QB). Averaging the raw numbers let Draft Sharks decide the
aggregate score by itself, and a player with no Draft Sharks row (weight redistributed onto the small
Yahoo ranks) leapfrogged identical peers. The site re-ranks Draft Sharks within the RB/WR/TE ("FLEX")
and QB groups (`rescaleDraftSharksRanks` in `site/src/lib/blend.ts`) before blending; Rankings still
displays the raw value and nothing stored in `in_season_rankings.rank` is rescaled.

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

## Justin Boone & Joel Smyth weekly rankings (`src/sources/yahoo_weekly_consensus.py`)

**Also pulled (added 2026-09-18, archival only): Matt Harmon (`747`), Scott
Pianowski (`9`), Hayden Winks (`7666`)** — the other three of Yahoo's five
analysts, from the same responses, stored under `source` = `harmon` /
`pianowski` / `winks` in `in_season_rankings` (no schema change). The site
ignores them: `useWeeklyRows.ts` filters to `draftsharks`/`boone`/`smythe`.
Boone/Smyth's cross-check against each other in `pull_week.py` doesn't apply
to them.

**Supersedes an earlier FantasyPros-widget-based implementation** (this doc
used to describe separate `boone_weekly.py`/`smythe_weekly.py` modules
hitting `partners.fantasypros.com/api/v1/consensus-rankings.php` — that
approach is gone; both experts are pulled through one shared module now).

`GET https://sports.yahoo.com/api/fanPro/` — the same public, unauthenticated
endpoint `Draft/src/sources/yahoo_consensus.py` uses for the draft-day board,
extended here with a `week` param. Both Boone's and Smyth's individual ranks
come back from a single response per position/scoring call — their expert
ids (`317` Boone, `7604` Smyth) are resolved by name from the response's own
`expertNames` map, never hardcoded/guessed.

**Query params**: `sport=NFL`, `position`, `filters=9:317:747:7604:7666`
(all 5 of Yahoo's current analysts — required for the response to include
any `experts` data at all), `experts=show`, `expert=7261`, `scoring`
(`HALF`/`PPR`), `type=ST`, `week`, `wtype=ST`, `year`.

**`position` gotcha — confirmed live 2026-09-18**: `position=ALL` (what the
draft-day module uses) only works for `week=0` (preseason/draft); for any
in-season week it 500s (`{"error": "Failed to fetch fantasy rankings"}`).
There is no single-request "everyone" view in-season. What *does* work
in-season is `position=FLX` — a real, one-request RB/WR/TE-combined ranking
(QB excluded) that both Boone and Smyth populate (confirmed: ~150–240
players). `QUERY_POSITIONS` in this module is `["QB", "FLX", "K", "DST"]`,
not one call per real position — querying `QB`/`RB`/`WR`/`TE`/`K`/`DST`
separately (the original, pre-2026-09-18 approach) gave each position its
own independent 1..N ranking, so a weekly view showed an RB-1 *and* a WR-1
*and* a TE-1 simultaneously. Each player's real `position` field in the
response is unaffected by which query positions was used to fetch it (a
`FLX`-queried response still tags each row `RB`/`WR`/`TE` correctly) — only
`rank` changes meaning based on which position value was queried.

**Response shape** (one player, from a `position=QB` call):
```json
{
  "id": "17233", "name": "Lamar Jackson", "position": "QB", "team": "BAL",
  "rank": 1, "consensusRank": "1.40", "expertCount": 5,
  "byeWeek": 13, "opponent": "at IND", "percentOwned": 100,
  "experts": {"9": "1", "317": "3", "747": "1", "7604": "1", "7666": "1"}
}
```
`experts` maps expert id -> that expert's own rank for this player (not the
blended `consensusRank`, which is Yahoo's average across all listed
experts). No per-expert numeric projection is returned — only rank.

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

**Table header shape isn't consistent across positions either** — confirmed
live 2026-09-18: the RB breakdown for week 2 dropped the leading `Rk` column
entirely (header `['Player', 'HALF', 'PPR']`, 3 cells) while QB/WR/TE kept it
(`['Rk', 'Player', ...]`, 4 cells) on the same day. The parser accepts both
shapes (rank comes back `None` for the no-rank case) rather than failing the
whole position. When a Boone position fails with an "Unexpected table
header" error, fetch that position's live URL and diff the actual header
against both known shapes before assuming a bigger break — and check the
other 3 positions too, since Yahoo has changed shape asymmetrically before.

## CBS / FantasyPros / RSJ trade values (added 2026-09-17)

Three more trade-value sources. Originally captured for accuracy-analysis
only; **wired into the site's Trade Values page as of 2026-09-18** (see the
`site/src/lib/tradeValues.ts` note in the Supabase section below for how the
site picks the right column per scoring format from these differing labels).
All three share `in_season_trade_values` /
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

Both experts confirmed live and independent as of 2026-09-08 (`validate.py`'s
`check_not_identical_to_other_source` exists to catch a silent expert-id
fallback — flags, doesn't drop, a Smyth pull whose player order matches
Boone's beyond a small overlap threshold).

## Site: Trade Values page (`site/src/lib/tradeValues.ts`)

Pivots the long-format `in_season_trade_values_latest` rows (one row per
source per player) into one row per player with each source as a column,
plus a cross-source "normalized score" (each source's percentile rank,
averaged — trade-value charts use each source's own arbitrary numeric scale,
position-agnostic on purpose so e.g. an RB1 and a WR1 are directly
comparable, so percentile rank is what puts different sources' scales on the
same footing before averaging them).

**Scoring-format selection is label-driven, not a hardcoded per-source
table**: `valueForScoring` picks `value_col1`/`value_col2` by pattern-matching
the row's own `value_col1_label`/`value_col2_label` text (`/half/i` for
half-PPR, `/(ppr|full)/i` for full-PPR) rather than hardcoding which column
means what per source — sources spell this differently (Boone/CBS:
`HALF`/`PPR`; USA Today: `HALF`/`FULL`; RSJ: `PPR`-only; FantasyPros: a
single blended `VALUE`; QB across all sources: `1QB`/`2QB`, a league-size
split, not a scoring split). A source whose labels don't match either
scoring tag falls back to `value_col1` regardless of the toggle (QB,
FantasyPros) — nothing to switch between. A source that matches the *other*
scoring tag but not the requested one (RSJ under half-PPR) returns `null`
rather than reusing its one value under the wrong label, and the column
auto-hides (`sourcesWithData`) rather than showing an all-blank column.

**Draft Sharks "3D value" is a sixth source, but it isn't in
`in_season_trade_values`** — `TradeValues.tsx` pulls
`in_season_ros_rankings_latest`, keeps QB/RB/WR/TE rows for the active
scoring only (`dsRosToSourceRow`), and injects them into the pivot as
`source: 'draftsharks'` using `ds_value` (range roughly -116..100, so it leans
on percentile normalization like every other source). Only the *active*
scoring's rows may be fed to `pivotTradeValues` — it keys values by
`(player, source)`, so a second row for the other scoring would overwrite the
real value with `null`.

**PostgREST caps every response at 1000 rows, silently** — `.limit(5000)`
does not raise it, it just returns 1000 with no error. Full trade values
(~1,236 rows) and one week of weekly rankings (~1,400 rows: DS alone is ~900
incl. DL/K/DST) both exceed it; the symptom is a whole source or scattered
players missing (USA Today, Trevor Lawrence's DS row), not an error. Use
`fetchAllRows` (`site/src/lib/supabase.ts`, pages via `.range()`, needs a
unique `.order('id')`) for any query that can grow past 1000.

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
(`draftsharks`, `boone`, `smythe`, `harmon`, `pianowski`, `winks`) ever appear in that column, so lookups
here deliberately ignore `source`/`team` and match on normalized name only
(punctuation/case/suffix-stripped, both straight `'` and curly `'`/`'`
apostrophes since 2026-09-18 — two spellings of the same player were
silently splitting into two `canonical_name` rows before that fix).

**Alias targets are normalized too (2026-09-19).** `aliases.csv`'s `canonical_name` column is a
human-cased display name ("Cameron Skattebo"), and `canonical_name_for` used to return it verbatim
while a source that already spelled the full name took the no-alias path and got the normalized form
("cameron skattebo"): one player, two keys, listed twice on the site (Cam Ward, Cam Skattebo, Kenny
Gainwell). It now returns `normalize_name(alias_target)`, so a stored `canonical_name` is always the
lowercase normalized form. Supabase was backfilled the same day (3,217 rows across
`in_season_rankings` / `in_season_trade_values` / `in_season_ros_rankings`, 12 names); a capitalized
`canonical_name` in any of them is a regression. Local `data/processed/*.csv` were **not** rewritten and
may still hold the old capitalized names for those players.

**`canonical_name` alone is NOT a safe cross-source join/group key** — this
doc previously claimed name-only collisions "aren't a practical risk"; that
was wrong, confirmed live 2026-09-18: a real WR Justin Jefferson (MIN) and a
different real person, an LB also named Justin Jefferson, share a
`canonical_name`. Code that grouped rows by `canonical_name` alone (the
site's Weekly tab, `blendRosValues`) silently merged their two rows into
one, each stealing the other's data. The established fix is to join on
`(canonical_name, normalized_position)` instead — see
`normalizePosition`/`identityKey` in `site/src/lib/blend.ts` (also handles
Draft Sharks spelling defense `"DEF"` vs. Boone/Smyth's `"DST"`, so same-team
defenses still merge under the composite key) and the equivalent composite
key in `site/src/lib/tradeValues.ts`'s pivot. Any new code joining across
sources by name should follow this pattern, not `canonical_name` alone. This
still doesn't solve cross-dataset gaps like a player missing entirely from
one source's pull; see `docs/superpowers/specs/2026-09-12-supabase-foundation-design.md`
for what's explicitly out of scope.
