# Betting (BetHub) — Status

## Current state

Dormant. This is last season's prop-betting tracking tool, moved into `in-season/` on 2026-09-11 alongside `team-analyzer` as part of folder consolidation — not touched or updated for the current season. These knowledge files are a first pass for orientation, not a verified audit of whether the code still runs.

## Known open questions (not yet investigated)

- Whether the scrapers (`cbs.py`, `last5_yds.py`, `depth_chart.py`, `schedule.py`) still work against their target sites' current layouts — none have been run recently, and `cbs.py` already needed anti-bot-detection tooling (`undetected_chromedriver`) last time, suggesting CBS's site is actively hostile to scraping and may need more workarounds now.
- Whether `SuperBowl/scrape_action_superbowl.py` was a one-time build for a specific game or is meant to be reused for other high-profile matchups going forward.
- Whether the OCR dependencies in `requirements.txt` (`pytesseract`, `pillow`) were ever actually wired into a feature (e.g., reading picks from a screenshotted bet slip) — no script in the current file set obviously uses them, so this may be a planned-but-unbuilt feature from `betting_mvp.txt`'s wish list.
- Whether `betting_mvp.txt`'s full feature list (bulk paste of picks, like/love flagging, settlement tracking) is fully implemented in `bethub_app.py` or partially — worth a side-by-side check before assuming any specific feature exists.

## Recent history

No git history available (not a git repo) — dates are inferred from file modification times, which show the core app built in October 2025, most scrapers refreshed mid-December 2025, and the one-off Super Bowl scraper added February 2026 (around that season's Super Bowl). Nothing since. Treat any "last season" reasoning as approximate.
