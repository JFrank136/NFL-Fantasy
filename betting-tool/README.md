# Activate Virtual Env
.\.venv\Scripts\Activate.ps1

# Refresh yards-allowed rankings (one command)
python run_all.py --week 5

Runs cbs.py -> last5_yds.py -> process_betting_info.py (forces UTF-8 so the
scrapers' checkmark prints don't crash on Windows). Output: exports/betting_info.csv
(not data/betting_info.csv, which is the old pick log). Weights are LAST5_WEIGHT /
CBS_WEIGHT at the top of process_betting_info.py; --week only sets the week label.


## Prop value (projection vs. book lines)

`run_all.py` also runs `props_lines.py` (Action Network pass/rush/rec yard and reception lines across
DraftKings, FanDuel, BetMGM, Caesars, Fanatics, Hard Rock -> `data/prop_lines.csv`), `ds_projections.py`
(Draft Sharks per-stat weekly projections (incl. receptions) via `researchDepth=projections` ->
`data/ds_projections.csv`), and `prop_value.py` -> `exports/prop_value.csv`.

Best line = lowest over (or highest under) among books with odds >= -130. DS projections
are means and lines are ~medians, so `prop_value.py` calibrates each stat with a linear fit
of line on projection; `Fair_Line` is what the market "should" be for that projection and
`Edge_Yds/Edge_Pct` measure the distance from the best available line. Config (`MIN_ODDS`,
`MIN_BOOKS`, `MIN_LINE`) is at the top of `prop_value.py`.


## Snapshots and grading

`snapshot.py` (last step of `run_all.py`) saves an immutable copy of `prop_lines.csv`, `ds_projections.csv` and
`prop_value.csv` to `snapshots/<capture time>/` (skipped if unchanged). `python grade.py` grades the latest
pre-kickoff pick per week/player/stat against nflverse (`nflreadpy`) and writes `grades/graded_picks.csv` and
`grades/report.csv`. Results: win/loss/push/void/pending/unverified. Snap counts decide DNP (void) vs played-with-no-stats (graded on 0); a missing player is never silently a loss. `python snapshot.py --import-picks FILE` loads a past export (kickoff from the nflverse schedule, pregame assumed).
Units are hypothetical flat 1u at listed odds. Tests: `python -m pytest tests`. Needs `pip install nflreadpy`.
