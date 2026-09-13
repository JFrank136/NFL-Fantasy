# In-Season — Runbook

How to actually run and operate this pipeline. Paste any section of this
into a ChatGPT conversation to get talked through it without needing Claude
Code open.

## Normal operation: nothing to do

The whole pipeline already runs automatically, once a day at 6:15am, via a
Windows Task Scheduler job named `FantasyInSeasonPull` — no app, and no
Claude Code session, needs to be open for this to happen. It runs a script
that pulls the week's rankings and, if that succeeds, pushes the result into
Vampire (Jared's separate matchup tool). Under normal circumstances, this
section of the runbook only matters when something looks off and Jared wants
to check or force a re-run.

## Setup (one-time, already done — reference only)

- Requires Python (3.11, specifically) and Node.js installed, since one half
  of this workflow is Python and the push into Vampire is a Node script.
- Python dependencies: `pip install -r requirements.txt` from inside the
  `in-season` folder (installs `requests`, `beautifulsoup4`, and `pytest`).
- The push-to-Vampire half needs a Vampire-side `.env` file with Supabase
  (Vampire's database) credentials already filled in — this lives in the
  Vampire project, not in-season, and is a one-time setup that's already
  done.

## Force today's refresh manually

Use this if today's 6:15am automated run looks like it failed, or Jared just
wants fresh numbers right now. This does the full job: pulls this week's
rankings and pushes the result into Vampire.

```powershell
powershell -File "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season\scripts\scheduled_pull.ps1"
```

This writes a timestamped log file to `in-season/data/scheduled_run_logs/` —
check the newest file there if something looks wrong afterward. The log ends
with either "FINISHED OK" or "FINISHED WITH FAILURES".

## Pull a specific week's rankings only (no push to Vampire)

Useful for checking "has this analyst posted rankings for week N yet" or
re-pulling a single week without touching Vampire at all.

```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
python scripts/pull_week.py --week <N> --source draftsharks --scoring half-ppr,ppr
```

`--source` can be `draftsharks`, `boone`, `smythe`, a comma-separated list of
those, or `all` (the default). `--week` can be a single number, a comma
list, or `all` (the default — every remaining week of the season). Leaving
every flag off pulls everything the automated job would pull. The command
prints a running summary as it works and exits with a non-zero status if
anything failed validation — that's meant to be treated as "this needs
attention," not skimmed past.

## Push an already-pulled week into Vampire only

Useful if a pull already succeeded but the push into Vampire didn't happen
or needs to be redone (e.g. after fixing a Vampire-side issue).

```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\Vampire\matchup-tool"
node --env-file=.env scripts/refresh-weekly-projection.js "../../in-season/data/processed/rankings_long.csv" <N> half-ppr
```

This only ever updates Vampire's "current week projection" field for
players it can confidently match by name — it never touches anything else
about a player, and it refuses to make any changes at all if fewer than half
the expected players get matched (a likely sign of a name-matching or file
problem, not a genuine data gap). Only Draft Sharks feeds this push, since
it's the only source with an actual numeric point projection.

## Checking whether the last run actually worked

Two ways, in order of convenience:

1. Open `in-season/data/last_run_status.json` — a small file rewritten after
   every run, showing `"ok": true` or `false` for the run overall, plus a
   per-week/source/scoring breakdown of exactly which pulls succeeded or
   failed and why.
2. Open the newest file in `in-season/data/scheduled_run_logs/` for the full
   play-by-play, including the Vampire push step.

## Running the automated tests

Confirms the pipeline's parsing and validation logic still works as
expected — mainly useful after changing any source module.

```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
pytest
```

## A known operational risk worth understanding

Boone and Smyth are fetched from a Yahoo backend endpoint that isn't an
official public API — Yahoo could change its shape at any time without
notice, same general risk as any unofficial-endpoint scraper. Draft Sharks'
weekly-rankings endpoint carries the same kind of risk. If a pull starts
failing that used to work, "the source changed something on their end" is a
reasonable first hypothesis, worth checking against the log's specific error
message before assuming a bug in this project's own code.
