# Betting (BetHub) — File Guide

## Top level

- **`bethub_app.py`** — the main Streamlit application. Defines the SQLite schema (a `picks` table: week, game, team, player, pick text, source, like/love flags, notes, timestamps) and the interactive UI for entering, browsing, and filtering picks. Uses `rapidfuzz` for fuzzy-matching player names (likely for matching a typed player name against the roster to infer their team). This is the one file Jared actually runs day-to-day.
- **`betting_mvp.txt`** — Jared's own plain-English project brief: the problems he was solving, the MVP requirements, and the planned feature list. Useful as a statement of intent — worth checking against what `bethub_app.py` actually implements, since a plan doc like this can drift from the code over time.
- **`bethub.db`** — the live SQLite database file. This is data, not code — it holds whatever picks and settings Jared entered last season. Treat it as season-specific state, not something to read for logic.
- **`load_data.py`** — loads CSV files (from `data/`) into `bethub.db`. This is the bridge between the standalone scrapers below and the app's database.
- **`README.md`** — currently just a one-line note on activating the Python virtual environment; not a real usage guide.
- **`requirements.txt`** — Python dependencies: `streamlit` (the app framework), `sqlalchemy` (database access — though `bethub_app.py` also uses raw `sqlite3` directly), `pandas`/`beautifulsoup4`/`requests` (scraping and data handling), `rapidfuzz` (fuzzy name matching), `pytesseract`/`pillow` (OCR — likely for pulling picks from screenshotted bet slips, though no script in this folder obviously uses it yet), `openpyxl` (Excel file support, probably a holdover from the old Excel-based workflow).

## Data-gathering scripts (each runs independently, producing a CSV)

- **`cbs.py`** — `CBSSportsScraper`: scrapes CBS Sports for "position vs. defense" stats (i.e., which defenses give up the most fantasy production to QBs/RBs/WRs/TEs), using `undetected_chromedriver` (a Selenium variant designed to avoid basic bot-detection) — implying CBS's site pushed back against simpler scraping.
- **`last5_yds.py`** — `FFTodayScraper`: scrapes FFToday for a similar "points allowed by position" stat, focused on a trailing 5-week window rather than full-season.
- **`depth_chart.py`** — scrapes ESPN's team roster pages to build a depth chart (player → team → position) across all 32 teams. This is the data source for BetHub's "auto-fill team from player name" feature.
- **`schedule.py`** — pulls the NFL game schedule from ESPN's API, parameterized by season year and season type (preseason/regular/playoffs).
- **`process_betting_info.py`** — combines the "last 5 weeks" and "full season" defense-strength stats into one blended number, using a manually-edited weighting ratio at the top of the file (the file's own comments recommend shifting the weight toward recent weeks as the season progresses — this is a knob Jared was expected to adjust by hand each week, not something automated).

## `SuperBowl/` — one-off addition

- **`scrape_action_superbowl.py`** — a standalone scraper for Action Network's picks for one specific game (originally built around a Super Bowl matchup), navigating from a picks hub page to a specific game's preview page and pulling structured data out of the page's embedded Next.js JSON. Takes a URL and an optional team name to select the right game.
- **`debug_action_hub.py`** — a debugging helper for the above, likely for inspecting the hub page's structure when the scraper needed adjusting.
- **`data/`** — output location for this scraper's CSVs.

This subfolder looks like a narrow, event-specific add-on rather than part of BetHub's regular weekly cycle — worth confirming with Jared whether it's meant to be reused for future single-game events or was a one-time build.

## `data/` and `exports/`

- **`data/`** — CSV outputs from the scrapers above (`cbs_yards.csv`, `last5_yds.csv`, `nfl_schedule_2025.csv`, `roster_latest.csv`, `betting_info.csv`, `uploaded_schedule.csv`) plus whatever gets uploaded through the app. This is generated/season data, not source code.
- **`exports/`** — presumably where the app writes exported picks or reports; empty or sparse as of this review.
