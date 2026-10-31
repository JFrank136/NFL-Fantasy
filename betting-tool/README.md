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


## Pick model (win probability, EV, shortlist)

`prop_value.py` picks the side and ranks by expected value (EV), using the frozen model in `models/v1/`. The original
Raw_Gap / Edge_Pct had no predictive power on the graded record (AUC ~0.51, the biggest edges hit worst), and the
market's median line beat the Draft Sharks projection on every stat, so `prop_model.py` anchors on the books. In
log-odds of the over: `market` (each book's de-vigged over/under, moved to the median line M, plus a credit for a
softer-than-median line) `+ skew` (per-stat right-skew correction) `+ projection tilt` (0.5 x the gap between the
projection and M), with the last two damped by 0.5. **The book being bet is left out of M and the de-vig average**, so a
book's own quote never vouches for itself. Run `python prop_value.py --explain "Player"` for the line-by-line arithmetic.

Per pick: `P_Win`, `BreakEven`, `EV_Pct`, `Tier` (Lean = EV >= 3%, >= 5 books, no flags; Watch = EV >= 1.5% or flagged;
Pass), `Flags`, `Hist` (graded record for that stat/direction), and where the edge comes from, in probability points:
`Mkt_Edge_Pts` (market probability minus break-even, so it includes the vig and is usually slightly negative),
`Skew_Pts`, `Proj_Pts`, summarised as `Source` = Pricing / Projection / Pricing+Projection / Base-rate.
`P_Mkt` / `EV_Mkt_Pct` are the same pick valued on books alone (no skew, no projection).
Outputs: `exports/prop_value.csv` (all), `exports/prop_shortlist.csv` (Lean + Watch), `exports/prop_predictions.csv`
(original, market-only and v1 picks side by side; copied into each snapshot).

### Frozen versions and the scorecard
`models/<version>/params.json` + `FROZEN.json` (hash, code commit, freeze time). A frozen version is never edited:
`load_params` refuses a modified file and `calibrate.py --version vN --write` refuses to overwrite. v1 was fitted on
weeks 6-7 (week 5 has picks but no quotes), with hyperparameters (w 0.5, shrink 0.5, ridge 30, tier cutoffs, top-20
rule) fixed in advance; **weeks 8 onward are its out-of-sample test**. `python scorecard.py` replays every snapshot
through the original model, a market-only baseline and v1, grades each model's top-20/week and its Lean/Watch set at
listed odds, labels weeks in-sample vs OUT-OF-SAMPLE, and reports Brier scores and closing-line value. Do not retune v1
on results; if a change is warranted, fit a new version and compare both going forward.

### Weekly routine
    python run_all.py --week N      # grades finished games, refreshes grades/universe.csv, pulls, snapshots, scores
    python scorecard.py             # after the week's games: ROI / hit rate / avg odds / N per model, by market and direction
    python calibrate.py             # diagnostics only (leave-one-week-out log loss); --version v2 --write freezes a NEW version
Closing lines are captured automatically (below). Outputs per week: `exports/prop_weekly_top.csv` is the concise list
(Lean picks only, best EV first, at most 20, never padded -- empty on a quiet week; `Mkt_Agrees` says whether the
market-only baseline makes the same bet); `prop_shortlist.csv` is Lean + Watch; `prop_value.csv` keeps every candidate.

### Keeping the test clean (weeks 8+)
Do not edit `models/v1/` (hash-checked), the tier cutoffs, the flags or the scoring functions in `prop_model.py` /
`prop_value.py` while v1 is being tested. `scorecard.py` prints a frozen-code check against the freeze commit and says
when the scoring code has changed. In-sample (weeks 6-7) v1 did NOT beat the market-only baseline: on the bets where
they differ v1 was 49.6% / -4.8% ROI vs 50.4% / -2.7% (121 bets; paired difference -0.02 units/bet, 95% CI -0.34..+0.30).
The out-of-sample weeks decide whether the skew and projection terms earn their place; if not, fall back to market-only.

### Closing lines (automatic)
Windows task `PropClosingLines` runs `pythonw closing.py --within-minutes 45` every 15 minutes, 6:00am-midnight daily, as
the logged-in user (no console window, no wake-from-sleep, runs on battery, needs network, 5-minute limit). Each run makes
one request and is idle unless a game kicks off within 45 minutes, so every game gets captures at roughly T-45/-30/-15;
`scorecard.py` uses the latest one before kickoff. Captures go to `closing/<time>/` (identical consecutive captures are
skipped); every run rewrites `closing/last_run.json`, and saves/errors append to `closing/closing.log`; transient network
failures are retried 3x. `scorecard.py` reports the heartbeat age and logged errors, and flags it STALE after 24h. The
task only runs while Jared is logged in and the laptop is awake (lid-closed Modern Standby can skip ticks); check
`Get-ScheduledTaskInfo PropClosingLines`. Reported per pick: `Line_CLV` (closing median minus the pick's line, in the
pick's favour) and `Close_EV_Pct` (the pick's EV at its odds under the closing no-vig probability).

### Status (weeks 6-7, in-sample)
Leave-one-week-out log loss: de-vigged market alone 0.690, with skew + tilt ~0.687 (coin flip 0.693). The projection's
link to actual-minus-line is weak (r ~ 0.1; negative for rush) and most v1 edges come from the projection and skew
terms, not from pricing. In-sample hit rates in the scorecard are not evidence; wait for week 8+.
