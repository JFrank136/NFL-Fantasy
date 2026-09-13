# Boone rest-of-season trade values + scheduled-pull notifications

Date: 2026-09-11

## Context

Jared sent 5 Yahoo article links: a full-PPR weekly-rankings roundup, and Justin
Boone's Week 1 rest-of-season trade value charts for QB/RB/WR/TE. He wants trade
values pulled into the pipeline every week, same as weekly rankings already are
(see `in-season/README.md`, `[[inseason-pipeline-status]]` memory — ROS rankings
was an explicitly open item). Separately, he's had no failure emails from
`FantasyInSeasonPull` and wants confirmation it's actually succeeding, plus a
success notification — but not a daily one; he suggested "every other day or
key days such as when rankings are first out, ROS rankings are first out,
gamedays."

Confirmed while investigating: today's run (2026-09-11 09:01) succeeded —
`LastTaskResult: 0`, 40/40 combos, both Vampire projection slots refreshed. The
task has been working; the silence was expected behavior (failure-only email).

## Part 1: Boone trade value ingestion

### Why a separate pipeline, not folded into `pull_week.py`

`pull_week.py`'s `RankingRow` shape (rank + projection per player) doesn't fit
trade-value data:
- It's "trade value points," not rank/projection.
- QB's table has different columns (**1QB** / **2QB** value) than RB/WR/TE
  (**HALF** / **PPR** value) — not even a uniform metric across positions.
- Fetch mechanism differs too: HTML scrape of a Yahoo article page (confirmed
  server-rendered, no JS needed — a plain `requests.get` with a real user-agent
  returns the full table), not the `api/fanPro/` JSON endpoint.

Forcing it into the existing shape would corrupt `RankingRow`'s meaning for
every other row. New, parallel unit instead — same conventions (append-only,
immutable raw snapshots, validate-then-write, non-zero exit on failure), own
schema and script.

### Discovery (URLs aren't stable/guessable week to week)

Fetch `https://sports.yahoo.com/author/justin-boone/`, regex-match links of the
shape `/fantasy/article/fantasy-football-week-\d+-justin-boones-(qb|rb|wr|te)-trade-value-charts-\d+\.html`
(confirmed present on the author page today for all 4 positions). Extract
position from the URL. If a position's link isn't present yet — Boone hasn't
published it for the current week — treat as "not yet available," same
soft-skip behavior the existing Boone/Smyth weekly-rankings pull already has
for an unpublished expert, not a hard error.

### Parsing

Confirmed table markup (identical structure across all 4 position pages):

```html
<h2 class="heading" id="jump-link-rest-of-season-{pos}-trade-values">...</h2>
<div class="content-table-wrapper">
  <table class="content-table">
    <tbody>
      <tr><td><p>Rk</p></td><td><p>Player</p></td><td><p>{COL1}</p></td><td><p>{COL2}</p></td></tr>
      <tr><td><p>1</p></td><td><p>Jahmyr Gibbs</p></td><td><p>86</p></td><td><p>89</p></td></tr>
      ...
```

One table per page. First row is the header — read `{COL1}`/`{COL2}` labels
from it directly rather than hardcoding "HALF"/"PPR" (QB's are "1QB"/"2QB").
Parse with `re`/`html.parser` or BeautifulSoup (whichever this project already
depends on — check `requirements.txt`), matching the existing
`yahoo_weekly_consensus.py` style: a typed exception
(`BoonTradeValueFetchError`), explicit shape checks before trusting the parse,
`time.sleep` between the 4 position requests.

### Schema — `TradeValueRow` (new, in `schema.py` alongside `RankingRow`)

```python
@dataclass
class TradeValueRow:
    season: int
    week: int              # week this chart was published for
    source: str             # "boone" (room to add another expert later)
    position: str
    pulled_at: str
    source_url: str
    rank: int | None
    player_name: str
    team: str | None
    value_col1_label: str   # e.g. "HALF" or "1QB"
    value_col1: float | None
    value_col2_label: str   # e.g. "PPR" or "2QB"
    value_col2: float | None
```

Kept generic (`value_col1`/`value_col2` + their labels) rather than
`half_ppr_value`/`full_ppr_value`, since QB's columns aren't PPR variants at
all — labeling them that way would misrepresent the data.

### Storage

- Raw: `data/raw/boone_trade_values/{season}/week{N}_{position}_{timestamp}.json`
  (immutable snapshot of the parsed table + source URL, matching the existing
  raw-snapshot convention).
- Processed: `data/processed/trade_values_long.csv`, append-only, same
  long-format-CSV convention as `rankings_long.csv`.

### Script — `scripts/pull_trade_values.py`

Mirrors `pull_week.py`'s shape: fetch all 4 positions for the current week,
validate (table found, row count sanity floor, values numeric), write raw +
processed, write its own `data/last_trade_values_status.json` (kept separate
from `last_run_status.json` since it's a different pipeline), non-zero exit on
any validation failure or unexpected error.

### Full-PPR rankings article link

Not scraped — it's the same data already live-pulled via
`yahoo_weekly_consensus.py`'s JSON API, just rendered as an article; scraping
it would be a second, redundant path. Confirmed with Jared: proceed without a
one-time spot-check against it (he picked "proceed" over "also run the
spot-check").

## Part 2: Scheduled-pull notifications

### Wiring `pull_trade_values.py` in

Added as its own step in `scripts/scheduled_pull.ps1`, right after
`pull_week.py`, writing to the same per-run log file. A trade-values failure
already triggers the existing `Send-FailureEmail` path (extend the "did
anything fail" check to include trade-values' exit code, same pattern as
`pullExit`).

### Success-email cadence (confirmed with Jared: gameday + first-publish)

New `Send-SuccessEmail` alongside the existing `Send-FailureEmail`, sent when
**either**:
1. **Gameday** — today is Thursday, Sunday, or Monday (`Get-Date`'s
   `DayOfWeek`).
2. **First publish this week** — this run is the first time a given
   `week{N}/{source}` combo (rankings *or* trade values) flipped from
   "not yet available" to a successful pull. Tracked via a small state file,
   `data/notify_state.json` — `{ "week1/draftsharks/half-ppr": "sent", ... }` —
   checked and updated by the PowerShell script after each run so a combo is
   never re-announced.

Email body: a short summary (combos pulled, any warnings, trade-value rows per
position) rather than the failure email's raw log tail — this one is a "good
news" ping, not a debugging aid.

### Second trigger — Sunday noon re-pull

Added mid-design (Jared, 2026-09-11): rankings get adjusted around midday on
Sundays as inactives/weather/late news comes in, so the existing single daily
6:15am trigger misses that update. Add a second Task Scheduler trigger to
`FantasyInSeasonPull` — Sundays at 12:00pm — same action (`scheduled_pull.ps1`),
same `RestartOnFailure`/`RunOnlyIfNetworkAvailable`/wake settings as the
existing trigger. Both triggers share one task and one log directory; the
noon run is a normal run through the same script, not a separate code path.

Interaction with the "first publish" notify state (above): the noon run uses
the same `data/notify_state.json`, so if 6:15am already caught this week's
first-publish for a combo, the noon run won't re-send that email — it'll only
email if it's *also* a gameday-cadence day (Sunday is), which it already would
under the existing gameday rule. No special-casing needed.

### Out of scope

- No change to the existing failure-email behavior/credential setup.
- Weekday/6:15am trigger is unchanged; Sunday gets a second trigger added
  (noon), not a schedule change to the existing one.
