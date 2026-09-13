# Betting (BetHub) — Runbook

## Running the app

From `in-season/Betting/`, with the project's virtual environment active:

```bash
.venv\Scripts\Activate.ps1
streamlit run bethub_app.py
```

Streamlit will open the app in a browser tab automatically (typically `http://localhost:8501`). The app reads and writes `bethub.db` in this same folder — no separate database server to start.

If the `.venv` doesn't exist or dependencies are missing:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Refreshing the supporting data (each is a standalone, manual step)

These aren't wired into the app or into each other — they're run individually, produce a CSV in `data/`, and then need `load_data.py` to get that CSV into the database the app reads.

**Defense-strength stats:**
```bash
python cbs.py
python last5_yds.py
python process_betting_info.py
```
`process_betting_info.py` has a manually-edited weighting constant at the top of the file (last-5-weeks vs. full-season split) that Jared adjusted by hand depending on how far into the season it was — check that value is sensible for the current week before trusting its output.

**Team rosters (for auto-filling a player's team when entering a pick):**
```bash
python depth_chart.py
```

**Schedule:**
```bash
python schedule.py
```

**Load whatever's been scraped into the database:**
```bash
python load_data.py
```

**One-off single-game scraper (Super Bowl example):**
```bash
cd SuperBowl
python scrape_action_superbowl.py --hub-url "https://www.actionnetwork.com/nfl/picks/game" --choose "Chiefs"
```

## Before relying on any of this again

This hasn't been run or verified since last season. Scraper scripts like these are fragile against site-layout changes by nature — expect at least `cbs.py` (which already needed `undetected_chromedriver` to get past CBS's bot detection) and `depth_chart.py` (scraping ESPN's roster pages) to need troubleshooting before they work again. Treat "run the scrapers" as a task to attempt and debug, not a step assumed to just work.
