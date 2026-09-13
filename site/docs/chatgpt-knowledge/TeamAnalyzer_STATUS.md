# Team Analyzer — Status

## Current state

Dormant. This is last season's trade-value tool, moved into `in-season/` on 2026-09-11 alongside the `Betting` tool as part of consolidating Jared's fantasy football projects into one folder. It has not been touched or updated for the current season. These knowledge files were created as a first pass — just enough for ChatGPT to understand what the tool is and orient a future conversation about updating it — not a deep audit of whether the code still runs correctly.

## Known open questions (not yet investigated)

- Whether the `scrapers/` (Boone and DraftSharks pullers) still work against each source's current site — they haven't been run recently, and scraper-target sites change layout without warning.
- Whether this should keep its own scraping path at all, given the new `in-season/` weekly-rankings pipeline (see the main in-season knowledge files) now pulls Boone and DraftSharks data on a schedule with validation. Rebuilding Team Analyzer to consume that pipeline's output instead of maintaining a parallel scraper would remove duplicated, unmaintained code — but no decision has been made on this.
- Whether the blend logic (60/40 DraftSharks/Boone weighting, the regression-based rescaling) still reflects how Jared wants to weight these two sources this season — last year's [[expert-weight-recalibration]] work (see that skill) was about the separate live-draft tool's consensus weights, not this tool, so it hasn't been cross-checked against Team Analyzer's blend.
- No indication of whether the "Trade Sandbox" (explicitly marked "beta" in the README) was ever used in earnest or just prototyped.

## Recent history

No git history available for this project (not a git repo) — dates are inferred from file modification times, which show active development in September-October 2025 and no changes since. Treat any "last season" reasoning as approximate.
