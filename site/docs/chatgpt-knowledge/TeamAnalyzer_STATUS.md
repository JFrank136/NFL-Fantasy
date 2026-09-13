# Team Analyzer — Status

## Current state

Dormant. This is last season's trade-value tool, moved into `in-season/` on 2026-09-11 alongside the `Betting` tool as part of consolidating Jared's fantasy football projects into one folder. It has not been touched or updated for the current season. These knowledge files were created as a first pass — just enough for ChatGPT to understand what the tool is and orient a future conversation about updating it — not a deep audit of whether the code still runs correctly.

## Known open questions (not yet investigated)

- This project's own standalone scrapers have since been removed; the open question is whether a rebuilt Team Analyzer should consume the new `in-season/` weekly-rankings pipeline's output (see the main in-season knowledge files) instead of any new scraping path — no decision has been made on this.
- Whether the blend logic (60/40 DraftSharks/Boone weighting, the regression-based rescaling) still reflects how Jared wants to weight these two sources this season — last year's [[expert-weight-recalibration]] work (see that skill) was about the separate live-draft tool's consensus weights, not this tool, so it hasn't been cross-checked against Team Analyzer's blend.
- No indication of whether the "Trade Sandbox" (explicitly marked "beta" in the README) was ever used in earnest or just prototyped.

## Recent history

No git history available for this project (not a git repo) — dates are inferred from file modification times, which show active development in September-October 2025 and no changes since. Treat any "last season" reasoning as approximate.
