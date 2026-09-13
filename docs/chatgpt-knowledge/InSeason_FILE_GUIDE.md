# In-Season — File Guide

A map of what lives where. Skips generated/cache files. Grouped by role in
the pipeline rather than alphabetically, since the pipeline's four stages
(fetch → normalize → validate → store) are the natural grouping.

## Entry point

**`scripts/pull_week.py`** — the command Jared (or the scheduled automation)
actually runs. Given a list of weeks, sources, and scoring formats, it loops
over every combination, fetches, normalizes, validates, and — if validation
passes — writes the result. It's deliberately opinionated about *which*
combinations make sense to attempt automatically: Draft Sharks publishes
rankings for future weeks, so an unattended "pull everything" run pulls
every remaining week for Draft Sharks, but Boone and Smyth only ever publish
the current week, so the same "pull everything" run only attempts those two
for this week — otherwise every single day would report the same permanent
"zero rows" failure for every future week, which would bury a real failure
under routine noise. It also writes a small status file after every run
(`data/last_run_status.json`) recording, per source/week/scoring, whether
that specific pull succeeded — this is what lets an unattended script
programmatically check "did today's run actually work" without reading
console output.

**`scripts/scheduled_pull.ps1`** — the script Windows' own Task Scheduler
runs automatically, with no Claude or app involvement at all. It runs
`pull_week.py`, and then — only if the current week's Draft Sharks half-PPR
pull succeeded — goes on to push the result into Vampire (see below). Every
run's full output is logged to a timestamped file so a later check can see
exactly what happened without having watched it run live. This script's
existence is itself a reliability decision: it's the backstop that keeps the
weekly pull going even on days Jared never opens Claude Code or any app.

## Fetching (one module per source)

**`src/sources/draftsharks_weekly.py`** — talks to Draft Sharks' weekly
rankings feed directly. This is a page endpoint that isn't real JSON — it's
a fragment of HTML meant to be inserted into the page's table, one block per
player — so this module parses that HTML rather than deserializing JSON. It
paginates automatically (repeatedly asking for more players) until Draft
Sharks stops returning new ones. Notably, this is the only source with a
real point projection, floor/ceiling range, and tier information; the other
two sources only provide a rank.

**`src/sources/yahoo_weekly_consensus.py`** — fetches both Boone's and
Smyth's rankings from a single shared mechanism: a backend data endpoint
Yahoo's own website uses internally, rather than the visible web page
(which blocks plain automated requests). One request per player position
returns every analyst's individual rank for players at that position, and
this module picks out the one named analyst it was asked for by matching
their name in the response rather than hardcoding their numeric ID — this
matters because Yahoo could change or reassign a numeric analyst ID at any
time, and matching by name keeps the code working even if that happens.
This module — not two separate ones — is what actually handles both Boone
and Smyth; the project's own `docs/DATA.md` describes an earlier plan to use
a different endpoint (FantasyPros' own widget backend) with separate
per-analyst files, but the implementation moved to this shared Yahoo
approach instead. Treat this file, not that older section of DATA.md, as
the accurate description of how Boone/Smyth data is actually fetched today.

## Normalizing and defining the shared shape

**`src/schema.py`** — defines the one common row shape (season, week,
source, scoring format, when it was pulled, player identity, rank,
projection, etc.) that every source's data gets converted into. This is
what lets every downstream tool treat "a row of rankings data" the same way
regardless of which of the three sources it came from.

**`src/normalize.py`** — the translation layer: takes what each source
module returns in its own particular shape and converts it into that one
shared row shape. Small and mechanical by design — if a mapping here looks
wrong, the fix belongs here, not in the tools that consume the data.

**`src/season_config.py`** — answers "what NFL week is it right now, and
which weeks should still be actively refreshed." Because NFL weeks run
Tuesday-to-Tuesday (the last game of a week is the Monday night game, and
the next week's slate starts the following Tuesday), this file defines that
window explicitly rather than relying on a naive date calculation. It needs
one manual one-line update at the start of each new season (the date of the
Tuesday on or before that season's kickoff).

## Validating

**`src/validate.py`** — the safety layer described in OVERVIEW.md. Runs a
handful of checks on every single pull before anything gets written: is the
pull empty, are required fields (player name, position) missing, are
players duplicated within one pull (Draft Sharks' own site has been
observed to occasionally list the same player twice — this is treated as a
known real-world quirk to clean up automatically, not a bug in this
project's own code, so it's fixed with a warning rather than failing the
whole pull over it), are there suspiciously few players at a given position
(a sign of a partial/broken pull), and — specific to the Smyth situation —
does this pull's top players match another analyst's pull suspiciously
closely, which would suggest an unpublished analyst ID silently fell back to
someone else's default data instead of erroring outright. Checks are split
into "errors" (bad enough that the pull is not written at all) and
"warnings" (worth a glance, not bad enough to block the run).

## Storing

**`src/storage.py`** — writes two kinds of output, both append-only by
construction: an untouched, timestamped raw snapshot per pull (kept forever,
useful for debugging or re-processing later without needing to re-fetch),
and an append to one long-running processed file that accumulates every
pull ever made. Re-pulling an already-pulled week never deletes or
overwrites what was there before.

## Documentation

**`README.md`** — the project's own front door: what it is, why it's
separate from Draft, where data comes from, and the basic usage command.

**`docs/DATA.md`** — a technical reference recording the exact request/
response shape of each source's endpoint, written so a future session
doesn't have to re-derive these by trial and error. Its Draft Sharks section
is accurate and current; its Boone/Smyth section describes an earlier,
since-abandoned endpoint choice (see the note under
`yahoo_weekly_consensus.py` above) — useful as history, but not a reliable
description of the code as it exists today.

## Tests

**`tests/`** — one test file per source module plus one each for
`pull_week.py`, `season_config.py`, and `validate.py`. These exist to catch
a source silently changing its response shape (a very real risk for
unofficial, unauthenticated endpoints like these) and to lock in the
tricky date-math and validation-severity logic described above.
