# In-Season — Overview

## What this is

Jared runs a fantasy football league and already has a preseason draft-day
tool called "Draft" (a separate project). "In-season" is the next phase:
once the season starts, the useful question changes from "who should I
draft" to "who should I start this week / should I make this trade / who
should I pick up off waivers." Those weekly decisions all need the same raw
ingredient — fresh weekly player rankings and projections — refreshed every
week rather than pulled once. In-season is the pipeline that fetches that
weekly data and the (still-thin) start of the tools that will consume it.

The project itself is just a Python data pipeline right now. The actual
start/sit, trade, waiver-wire, and rest-of-season "tools" are aspirational —
the README lists them as the point of the project, but only the data layer
underneath them has been built so far.

## Why this is a separate project from "Draft"

Draft builds one thing once a year: a ranked board for draft day, built from
a snapshot of expert rankings pulled a single time. In-season pulls the same
kinds of expert rankings, but weekly, all season long, and — critically —
keeps every week's pull as its own historical record instead of overwriting
last week's numbers. A week's rankings get revised multiple times before
that week's games kick off (injuries, depth chart news, etc.), and Jared
wants to be able to see how a projection moved over the days leading into a
game, not just know the final number. That "keep history, never overwrite"
requirement is the main architectural fact that shapes everything else in
this project — it dictates append-only storage rather than a simple
overwrite-in-place database table.

## Where the data comes from

Three ranking sources, described in plain terms:

- **Draft Sharks** — a fantasy football analytics site. Its weekly rankings
  page is reachable directly (no login), and it returns Draft Sharks' own
  blended "3D projection" (a composite of multiple models) plus a
  floor/ceiling range, tiers, and matchup context — the richest of the three
  sources by far, and the only one with an actual point projection.
- **Justin Boone** — an individual fantasy analyst. His rankings are
  syndicated through Yahoo Sports, and this project reads them from Yahoo's
  own backend data endpoint rather than scraping Yahoo's web page (Yahoo's
  actual page content is blocked to plain automated fetches). Boone's feed
  gives a rank per player, not a numeric point projection.
- **Joel Smyth** — a second individual analyst, pulled through the same
  Yahoo mechanism as Boone. As of this writing, it isn't fully confirmed
  that Smyth's true weekly rankings are even available yet this season (his
  own site said "PPR rankings coming Thursday"), and there's a specific
  known risk that an unpublished analyst ID silently returns someone else's
  data instead of erroring — see STATUS.md and the built-in safeguard for
  this.

Both scoring formats the league might care about — half-PPR and full PPR
("PPR" meaning points-per-reception, a scoring rule that awards a point for
every catch, "half-PPR" awarding half a point) — are pulled for each source
every time.

## Architectural shape

Four stages, each independently testable:

1. **Fetch** — one module per source, each responsible only for calling that
   source's endpoint and parsing its particular response shape into a
   consistent small set of fields.
2. **Normalize** — takes whatever each source module returned and maps it
   into one shared row shape used everywhere downstream, so nothing later in
   the pipeline needs to know or care which source a row came from.
3. **Validate** — before anything gets written anywhere, a pull is checked
   for signs of being broken or suspicious: too few players, missing names,
   duplicate players, or a pull that looks suspiciously identical to a
   different analyst's pull (the Smyth/Boone fallback risk mentioned above).
   Jared has been explicit that a silently-bad week of data is worse than a
   loud failure, since missing real pre-game rankings can't be recovered
   after the fact — so validation failures stop the pipeline from writing
   anything for that pull rather than writing questionable data.
4. **Store** — writes two things: an untouched raw snapshot of exactly what
   the source returned (for later debugging or re-processing), and an
   append to one long-running spreadsheet-style file that every tool reads
   from. Nothing is ever overwritten; a re-pull of an already-pulled week
   just adds new rows timestamped later.

## Constraints and decisions worth knowing

- **No database yet, on purpose.** Everything lives in local files. A real
  database (Supabase, the same one the Draft and Vampire projects already
  use) is planned but deliberately deferred until the file-based version has
  proven itself against a few real weeks of live data — Jared didn't want
  to design a schema before knowing what the data actually looks like in
  practice.
- **Downstream integration with "Vampire."** Vampire is Jared's separate
  in-season matchup/strategy tool for his league (a different project, with
  its own database). This pipeline's Draft Sharks projections are pushed
  into Vampire's own player-value table every day, as a targeted update to
  just the "current week's projection" field — never a wipe of Vampire's
  other data. Boone and Smyth don't feed Vampire this way today since they
  only carry a rank, not a point value that could be blended into anything
  numeric.
- **Reliability is treated as the core requirement, not a nice-to-have.**
  Jared has said outright that missing a week's pre-game rankings is
  unrecoverable — there's no "try again later" once games start. That's why
  validation is strict, why raw snapshots are kept forever, and why the
  scheduled automation (see RUNBOOK.md) was deliberately built with a
  redundant backup mechanism until the primary one proved itself reliable.
