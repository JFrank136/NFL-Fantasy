# In-Season — Status

Last refreshed: 2026-09-10. This file goes stale fastest of the four — if
it's been more than a couple of weeks, treat the specifics below as
probably outdated and confirm before relying on them.

## What's actually working today

The core weekly pull-and-push pipeline is built and has completed a real,
successful, fully unattended run: on 2026-09-09 at 9:17pm, the scheduled job
pulled all 40 source/week/scoring combinations it attempts automatically
(every remaining week of the season for Draft Sharks; the current week only
for Boone and Smyth), and then successfully pushed Draft Sharks' week-1
projections into Vampire, matching 439 of 541 Vampire players by name (81%
— the rest are bench/inactive players not present in a given week's
rankings, which is expected, not a failure).

Automation is handled by a single Windows Task Scheduler job
(`FantasyInSeasonPull`, daily 6:15am) that runs independently of any app or
Claude Code session. An earlier, redundant in-app Claude-side scheduled task
covering the same job was deliberately deleted on 2026-09-09, once the
Windows-level job had proven itself reliable — per Jared's general
preference (see his automation-reliability expectations) of keeping a
backup trigger only until the primary one is proven, then dropping the
backup rather than running both forever.

## A live issue as of this morning (2026-09-10)

The most recent recorded run (this morning, ~9:00am) failed completely — all
40 combinations errored with a DNS resolution failure (unable to resolve
either `www.draftsharks.com` or `sports.yahoo.com`), meaning nothing was
pulled or pushed today. This looks like a network connectivity problem at
the moment the job ran, not a code or source-side problem — the previous
evening's run succeeded end-to-end using the identical code path. Worth
confirming whether this was a one-off (e.g. the machine was asleep, or WiFi
was briefly down at 6:15am) or something that keeps recurring; if it keeps
happening, it may need its own handling (e.g. retry logic, or an alert
separate from just the log file).

## The Vampire integration, specifically

This is the one actively-evolving piece worth tracking closely. Current
state: only Draft Sharks' projection feeds Vampire, via a script that
updates just the "current week's projection" field on Vampire's existing
player records — it never recreates or wipes anything else about those
records. Boone and Smyth don't feed into Vampire at all yet, because
neither provides a numeric point value in this pipeline (only a rank), and
there's nothing to blend a rank into. Manual copy-paste commands for
forcing this refresh (full pipeline, pull-only, or push-only) now live in
Vampire's own `INSTRUCTIONS.md` file under "Weekly rankings data refresh."

## Still open / not built yet

- **Rest-of-season rankings**: not built at all. Draft Sharks has a separate
  section of its site for rest-of-season (as opposed to single-week)
  rankings that hasn't even been inspected yet.
- **Smyth's data reliability is unconfirmed.** Full-PPR pulls for Smyth
  have succeeded without erroring, but it's never been independently
  verified that they're genuinely his own distinct rankings rather than a
  silent fallback to someone else's default data (the specific failure mode
  the validation logic in `validate.py` was built to catch and flag, not to
  fully rule out on its own — see FILE_GUIDE.md).
- **The other in-season tools don't exist yet.** Start/sit, trade, waiver
  wire, and rest-of-season tools — the actual stated point of this project
  per its own README — are still just "the data layer underneath them
  exists." No tool-level logic has been written.
- **Supabase migration deferred.** Everything is still local files by
  deliberate choice, until the schema has proven itself against more real
  weeks of live data.
- **Cross-source name-matching for in-season's own future use** (blending
  Boone + Smyth + Draft Sharks together for the in-season tools themselves,
  as opposed to just Draft Sharks feeding Vampire) doesn't exist yet — the
  only name-matching happening today is the one-directional feed into
  Vampire, which reuses Vampire's own existing matching logic rather than
  this project having its own.

## A documentation note worth knowing

`docs/DATA.md` (the technical reference for each source's request/response
shape) describes an earlier plan for fetching Boone and Smyth through a
different endpoint (FantasyPros' own widget backend, with two separate
source files) than what was actually built. The implementation ended up
using a single shared module against a Yahoo backend endpoint instead,
because it was judged the safer approach — this is reflected accurately in
FILE_GUIDE.md above, but if DATA.md itself is ever consulted directly, treat
its Boone/Smyth section as history rather than current fact.

## Why reliability keeps getting so much attention here

Worth repeating because it explains a lot of the design choices elsewhere
in this project: Jared has said explicitly that missing a week's pre-game
rankings is unrecoverable — there's no way to get a "what were the
projections right before kickoff" snapshot back after the fact. That's the
reasoning behind strict validation (failing loudly rather than writing
questionable data), permanent raw snapshots, and the redundant-then-pruned
scheduling approach described above.
