# Betting (BetHub) — Overview

## What this is

"Betting" (internally called **BetHub**) is Jared's personal tool for tracking NFL player-prop betting picks — a project separate from his fantasy football leagues, though it lives alongside them since it's built on similar data (player stats, matchups, schedules). It's a local desktop-style app (built with Streamlit, a Python framework for quick data-entry/dashboard tools) backed by a local SQLite database. It was moved into `in-season/` on 2026-09-11 as part of consolidating his fantasy-football-adjacent tools into one place — it's not part of the new in-season rankings pipeline, just stored near it now.

It has not been updated for the current season and is expected to need rework before use.

## Why it exists

Before this tool, Jared's workflow for tracking prop bets was manual and scattered: he'd gather betting picks from various handicappers and communities (Twitter/X accounts, Reddit, named sources like "MattLocks," "CB Mismatch," "NovelCalendar," "DoughNation," "Hit Rate"), then hand-enter them into Excel — including manually figuring out which NFL team each mentioned player was on, and manually tracking each bet's status (yards needed, potential payout) as games played out, removing settled bets by hand. That was the time sink he built this to remove.

BetHub's design goals (from the project's own planning notes): save every entry automatically to a local database (no manual saves, nothing lost), work fully offline, make entering a pick fast, and support quick filtering by game/team/source.

## How it's meant to work

The intended workflow, as designed:

1. **Enter picks** — either one at a time through a form, or by pasting a batch of picks copied from Reddit/X in bulk, tagging them with a source.
2. **Auto-resolve the team** — when a player name is entered, the app tries to look up which team that player is on (using roster/depth-chart data pulled in separately) so Jared doesn't have to type it himself.
3. **Support research** — separate from pick entry, the tool also pulls in supporting stats: which defenses are weak against which positions (from CBS Sports and FFToday), team schedules, and in at least one case, another site's own consensus picks for a specific event (a Super Bowl scraper).
4. **Track and filter** — picks are stored with metadata (week, game, team, player, source, like/love flag, notes) so they can be filtered and reviewed later, and marked settled.

## Architecture, in plain terms

There's one main Streamlit app (`bethub_app.py`) that is the actual interactive tool — it owns the SQLite database schema and the pick-entry/browsing UI. Everything else in the project is a **supporting data-gathering script**, run separately and independently of the app, to produce CSV files that either get loaded into the database or referenced during analysis:

- Web scrapers that pull opponent-strength stats from CBS Sports and FFToday.
- A scraper for NFL team depth charts (which players are on which team, at which position) — this is what feeds the "auto-fill team from player name" feature.
- A scraper for the NFL game schedule.
- A separate weighting/blending script that combines "last 5 weeks" and "full season" stats with a configurable ratio, meant to be tuned as the season progresses.
- A one-off scraper (in a `SuperBowl/` subfolder) for pulling Action Network's picks for a single high-profile game — this looks like a narrow, one-time addition rather than part of the regular weekly workflow.

None of these scrapers talk to each other directly — they each write a CSV, and a separate `load_data.py` script is what actually loads CSVs into the SQLite database the Streamlit app reads from.
