# Draft Sharks ROS rankings pipeline

Date: 2026-09-16

## Context

The site's Rankings page (ROS tab, planned but not yet built) needs Draft
Sharks' rest-of-season value and ceiling/upside, which don't exist anywhere in
the pipeline today: `in_season_rankings` only holds weekly data (from
`weekly-rankings/load-rows`), and `in_season_trade_values` only holds Boone's
trade charts. Draft Sharks publishes a separate ROS rankings report
(`ros-rankings/load-rows`) with its own blended trade value (`dsValue`),
floor/ceiling projections, strength of schedule, and other fields that don't
exist in either table today.

This spec covers pulling that report into the pipeline, following the
conventions already established by weekly rankings and Boone trade values
(see `docs/superpowers/specs/2026-09-11-boone-trade-values-and-notify-design.md`).
Site/frontend work (an ROS tab in `site/src/pages/Rankings.tsx`) is
explicitly out of scope — this spec ends at clean, validated data landing in
Supabase.

## Endpoint (confirmed via browser network inspection)

```
GET https://www.draftsharks.com/ros-rankings/load-rows
    ?offset=0&limit=300&fantasyPosition=&pprSuperflexSlug=half-ppr&sort=-dsValue&researchDepth=rankings
```

- Same pagination pattern as `src/sources/draftsharks_weekly.py`: increment
  `offset` by rows returned, stop when a page returns 0 rows.
- `pprSuperflexSlug`: confirmed values `half-ppr` and `ppr` (pull both, same
  as weekly).
- `fantasyPosition=""` (empty) returns all positions in one paginated pull —
  confirmed counts in one sample page: RB 81, WR 77, QB 33, TE 26, plus
  LB/DL/DB/K/DEF (IDP/kicker/defense). Only QB/RB/WR/TE are kept, matching
  the rest of the pipeline's scope.

Row shape is the same `tbody[data-player-row]` HTML fragment structure as
weekly rankings — same BeautifulSoup parse:

- `data-key` → `source_player_id`
- `data-player-name` → player name
- `data-fantasy-position` → position
- team badge `img src="/img/icons/teams/CIN.svg"` → team (same regex as
  weekly: `/teams/([A-Z]+)\.svg`)
- `data-tier-overall` / `data-tier-positional` → tiers
- `.rank-index span` text → rank
- `data-attribute` cells:
  - `rosWeeklyPts` → ROS weekly points projection
  - `rosWeeklyFloorPts` → floor
  - `rosWeeklyCeilingPts` → ceiling/upside (the field the site's ROS tab
    needs and doesn't have today)
  - `dsValue` → Draft Sharks' single blended ROS trade value (their "3D
    value" score — the number to use as "Draft Sharks ROS value" for
    blending with Boone's trade value later)
  - `strength_of_schedule` → SOS %, e.g. `"-3.9%"`
  - `player.team.bye` → bye week
  - `games_played` → projected games played rest of season
  - `player.sipPlayerProfile.injury_prob` → injury risk (format
    unconfirmed — no live sample seen yet; see Schema section)

Confirmed no existing field elsewhere in this pipeline duplicates injury
risk, so this isn't redundant with anything already pulled.

## Architecture

A new parallel pipeline unit — same shape as the Boone trade-values
pipeline: its own source module, its own row schema, its own script, its own
status file, its own Supabase table. Nothing about the existing
weekly-rankings or trade-values pipelines changes.

```
draftsharks_ros.py (fetch + parse)
   -> normalize.draftsharks_ros_to_rows() -> RosRankingRow
   -> validate.validate_ros_rankings()
   -> storage: raw snapshot JSON + ros_rankings_long.csv (append-only)
pull_draftsharks_ros.py (orchestrates the above, writes last_draftsharks_ros_status.json)
push_to_supabase.py (extended: new CSV -> in_season_ros_rankings table)
scheduled_pull.ps1 (new step; status merged into the existing email)
```

### Why a new script, not folded into `pull_trade_values.py`

`pull_trade_values.py`'s shape (per-position URL discovery on Boone's Yahoo
author page, one HTML article scrape per position) doesn't fit this source
at all: Draft Sharks ROS is a single stable, unauthenticated JSON-backed
endpoint pulling all positions in one paginated call per scoring slug — the
same shape `pull_week.py` already has for weekly rankings, just pointed at a
different endpoint and table. A new script mirroring `pull_week.py` is a
better fit than bending `pull_trade_values.py`'s discovery logic to a source
that doesn't need discovery.

### Why a new table, not extending `in_season_trade_values`

`in_season_trade_values`'s `value_col1`/`value_col1_label` +
`value_col2`/`value_col2_label` pattern could arguably fit `dsValue` alone
(as a single labeled value column), but the table has no columns at all for
floor/ceiling/SOS/games-played/injury-risk, and forcing those in would
misshape a table whose whole point is "rank + two source-labeled value
columns." A new table mirroring `in_season_rankings`'s shape (rank,
projection, floor/ceiling, tier, bye) — scoped to ROS instead of a specific
week, plus the extra Draft-Sharks-specific fields — fits cleanly and matches
this codebase's existing pattern of "one table per data *shape*, not per
source": `in_season_rankings` and `in_season_trade_values` are both already
generic multi-source tables (`source` column) even though only one or two
sources populate them today. The new table follows the same convention:
`in_season_ros_rankings`, `source='draftsharks'` today, room for another ROS
source later without a schema change.

## Schema

**`src/sources/draftsharks_ros.py`** — new module, structured like
`draftsharks_weekly.py`:

```python
@dataclass
class DraftSharksRosRow:
    source_player_id: str
    player_name: str
    team: str | None
    position: str
    rank: int | None
    tier_overall: int | None
    tier_positional: int | None
    strength_of_schedule: str | None
    bye: int | None
    games_played: int | None
    floor_proj: float | None      # rosWeeklyFloorPts
    projection: float | None      # rosWeeklyPts
    ceiling_proj: float | None    # rosWeeklyCeilingPts
    ds_value: float | None        # dsValue
    injury_risk: str | None       # player.sipPlayerProfile.injury_prob, raw/unparsed
```

`fetch_draftsharks_ros(scoring_slug, request_delay=0.5, session=None) ->
list[DraftSharksRosRow]` paginates exactly like
`fetch_draftsharks_weekly`, with `fantasyPosition=""` (all positions in one
call) and `sort=-dsValue`, then filters the parsed rows to
`{"QB", "RB", "WR", "TE"}` before returning (dropping LB/DL/DB/K/DEF).

`injury_risk` and `strength_of_schedule` are stored as raw text rather than
parsed to a number — SOS is confirmed as a string like `"-3.9%"`, and
`injury_prob`'s actual format hasn't been observed live yet. The
implementation should print a handful of real sample values for
`injury_prob` the first time it runs against the live endpoint so the type
can be tightened later if it turns out to be cleanly numeric; this spec
does not assume a format it hasn't seen.

**`src/schema.py`** — new `RosRankingRow`, added alongside `RankingRow` and
`TradeValueRow`, following the same `as_dict()` + column-order-assertion
pattern:

```python
ROS_RANKING_COLUMNS = [
    "season", "source", "scoring", "pulled_at", "as_of_week",
    "source_player_id", "player_name", "canonical_name", "team", "position",
    "rank", "tier_overall", "tier_positional",
    "projection", "floor_proj", "ceiling_proj",
    "ds_value", "strength_of_schedule", "games_played", "injury_risk", "bye",
]

@dataclass
class RosRankingRow:
    season: int
    source: str            # "draftsharks" (room for another ROS source later)
    scoring: str            # "half-ppr" | "ppr"
    pulled_at: str            # ISO 8601 UTC
    as_of_week: int           # season_config.current_week() at pull time
    source_player_id: str
    player_name: str
    canonical_name: str
    team: str | None
    position: str
    rank: int | None
    tier_overall: int | None
    tier_positional: int | None
    projection: float | None
    floor_proj: float | None
    ceiling_proj: float | None
    ds_value: float | None
    strength_of_schedule: str | None
    games_played: int | None
    injury_risk: str | None
    bye: int | None
```

`as_of_week` is a snapshot marker, not part of any uniqueness key — ROS
rankings aren't published per-week the way weekly rankings are (there's no
"not yet published for week N" state for this endpoint the way Boone/Smyth
have); a re-pull just appends a newer `pulled_at` for the same player, same
as every other append-only row here.

**`src/normalize.py`** — new `draftsharks_ros_to_rows(rows, season,
as_of_week, scoring, pulled_at) -> list[RosRankingRow]`, using
`canonical_name_for` exactly like every other normalize function.

## Storage

- Raw: `data/raw/draftsharks_ros/{season}/asofweek{N:02d}_{scoring}_{timestamp}.json`
  — immutable snapshot of the parsed rows, matching the existing raw-snapshot
  convention (`storage.raw_snapshot_path` gets a ROS-specific sibling
  function, same pattern as `trade_value_raw_snapshot_path`).
- Processed: `data/processed/ros_rankings_long.csv`, append-only, same
  long-format-CSV convention as the other two processed files
  (`storage.append_ros_rankings_processed`, mirroring
  `append_trade_values_processed`).

## Validation

New `validate.validate_ros_rankings(rows, position_floors=None) ->
list[ValidationIssue]`, modeled on `validate_pull` (not
`validate_trade_values`) since this pulls all positions in one call, the
same shape as weekly rankings:

- `check_nonempty` equivalent (zero rows = error)
- blank `player_name` / `position` checks = error
- `dedupe_players` (reusing the existing function — Draft Sharks' own site
  has shown duplicate-row bugs on the weekly endpoint before, plausible here
  too) run before...
- `check_position_counts` reusing the existing `MINIMUM_POSITION_COUNTS`
  floors (QB 20, RB 30, WR 30, TE 10) = warning if under
- No `expect_projection` check needed — Draft Sharks always has projections,
  unlike the Yahoo-expert weekly rows.
- No `check_not_identical_to_other_source` — nothing to compare it against.

## Script — `scripts/pull_draftsharks_ros.py`

Mirrors `pull_week.py`'s shape:

- Loop over `["half-ppr", "ppr"]` (or `--scoring` override, matching
  `pull_week.py`'s CLI convention).
- For each: fetch -> normalize -> validate -> print issues -> write raw
  snapshot + append CSV if no errors.
- Non-zero exit if any scoring slug has a validation error or unexpected
  exception (matching `pull_trade_values.py`'s exit-code contract).
- Writes `data/last_draftsharks_ros_status.json`:
  ```json
  {
    "run_at": "...",
    "ok": true,
    "combos": {
      "week3/draftsharks_ros/half-ppr": "ok",
      "week3/draftsharks_ros/ppr": "ok"
    }
  }
  ```
  Deliberately reusing `last_run_status.json`'s exact `{run_at, ok, combos:
  {"week{N}/{source}/{scoring}": status}}` shape (not inventing a new one) —
  this lets `scheduled_pull.ps1`'s existing dynamic per-scoring-section
  source-discovery regex pick this file up as a second data source with a
  small extension rather than a bespoke branch, matching the project's
  existing preference for discovering sources from data instead of
  hardcoding them.

## Wiring — `scheduled_pull.ps1` + notify email

This is **not** a new email — it's a new row inside the one HTML status
email `scheduled_pull.ps1` already sends via `Send-SuccessEmailIfWarranted`
/ `Send-FailureEmail`.

- New step added after the existing `pull_trade_values.py` step, run the
  same way (`& $PythonExe "scripts\pull_draftsharks_ros.py" 2>&1 | ForEach
  -Object { Log $_ }`), its exit code folded into the existing `$anyFailure`
  check alongside `$pullExit` / `$tradeValuesExit`.
- `Get-StatusData`'s per-scoring-format loop (`Half PPR` / `Full PPR`
  sections) is extended to also read `last_draftsharks_ros_status.json`'s
  `combos`, using the same regex-based dynamic source discovery it already
  applies to `last_run_status.json` — so a "Draft Sharks Ros Rankings" row
  appears per scoring section automatically, no hardcoded label added to the
  script. (A small label-override map may be needed since
  `TextInfo.ToTitleCase("draftsharks_ros")` doesn't produce a clean display
  string on its own — a plan-time detail, not a design change.)
- First-publish / gameday cadence reuses the existing `data/notify_state.json`
  mechanism with new keys (`"rosrankings:week{N}/draftsharks_ros/{scoring}"`),
  same pattern `Send-SuccessEmailIfWarranted` already uses for rankings and
  trade values.
- A real failure in this step triggers the existing `Send-FailureEmail` path
  exactly like a `pull_week.py` or `pull_trade_values.py` failure does.

## Supabase

New migration `supabase/migrations/0002_ros_rankings.sql`:

```sql
create table if not exists in_season_ros_rankings (
  id bigserial primary key,
  season int not null,
  source text not null,
  scoring text not null,
  pulled_at timestamptz not null,
  as_of_week int not null,
  source_player_id text not null,
  player_name text not null,
  canonical_name text not null,
  team text,
  position text not null,
  rank int,
  tier_overall int,
  tier_positional int,
  projection double precision,
  floor_proj double precision,
  ceiling_proj double precision,
  ds_value double precision,
  strength_of_schedule text,
  games_played int,
  injury_risk text,
  bye int,
  created_at timestamptz not null default now()
);

create index if not exists in_season_ros_rankings_lookup_idx
  on in_season_ros_rankings (season, source, scoring, canonical_name);

create or replace view in_season_ros_rankings_latest as
select distinct on (season, source, scoring, canonical_name) *
from in_season_ros_rankings
order by season, source, scoring, canonical_name, pulled_at desc;
```

Note the latest view is distinct on `(season, source, scoring,
canonical_name)` **without** `as_of_week` in the key, unlike
`in_season_rankings_latest` (which includes `week`) — "latest ROS view for
this player" should mean the most recent snapshot regardless of which week
it was captured in, since ROS rankings describe the rest of the season, not
one specific week.

`push_to_supabase.py` gets a third CSV/table pair added to its existing
loop (`ROS_RANKINGS_CSV` -> `in_season_ros_rankings`, with its own
int/float column sets: `{"season", "rank", "tier_overall",
"tier_positional", "games_played", "bye", "as_of_week"}` /
`{"projection", "floor_proj", "ceiling_proj", "ds_value"}`), and a third
entry in the status-upsert loop (`(ROS_STATUS_PATH, "ros_rankings",
"combos")`, matching the existing two tuples exactly).

## Testing

Following existing test conventions (`tests/test_push_to_supabase.py` and
whatever exists for `draftsharks_weekly.py`/`boone_trade_values.py`):

- Unit tests for `_parse_page`-equivalent HTML parsing in
  `draftsharks_ros.py` against a saved fixture fragment (all
  `data-attribute` fields present, team-badge regex, rank parsing).
- Unit test confirming non-QB/RB/WR/TE positions get filtered out.
- Unit test for pagination stopping on a zero-row page.
- Unit test for `normalize.draftsharks_ros_to_rows` (canonical_name
  resolution, field mapping).
- Unit tests for `validate.validate_ros_rankings` (empty pull = error,
  position floor = warning, dedupe behavior).
- `push_to_supabase.py` test coverage extended to the third table the same
  way the existing two are covered.

## Out of scope

- Site/frontend work (the Rankings page's ROS tab) — a separate follow-up
  once this data exists in Supabase to build against.
- Blending Draft Sharks' `ds_value` with Boone's trade value into one
  combined "consensus ROS value" — this spec only gets the raw data landed;
  blending logic is future work.
- Parsing `injury_risk` into a normalized numeric/enum type — stored as raw
  text until a live sample confirms the format.
