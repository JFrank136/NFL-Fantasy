# Expert accuracy evaluation and shadow weighting

Code: `src/expert_eval/`. CLI: `scripts/run_expert_eval.py` (`--backtest` walk-forward test, `--audit`
leakage/permutation/outlier/policy audit, `--full` re-evaluate every final week, `--local-only` dry run).
Runs automatically as a step in `scripts/scheduled_pull.ps1` (see Operations). Site page: **Expert Accuracy**. Tests: `tests/test_expert_eval.py`,
`site/src/lib/expertEval.test.ts`.

**Shadow only.** Nothing here feeds the live Rankings blend, which still uses
`site/src/lib/consensusWeights.ts` until a promotion decision is made.

## What gets measured

- **Lock:** each player's last ranking published before that player's own kickoff (and no more than
  8 days old). Frozen into `expert_eval_snapshots`; raw `in_season_rankings` history is never edited.
  Player names are re-normalized at join time (`names.canon`), not rewritten in the data.
- **Scales:** same as the site -- QB against QBs; RB/WR/TE share the FLEX scale. Draft Sharks' overall
  rank is re-ranked within those groups (mirrors `rescaleDraftSharksRanks`). No rank-to-points curve is
  used in v1, so there is no leakage path from future weeks.
- **Primary metric -- lineup regret:** frozen, expert-neutral pool (QB 14 / RB 28 / WR 34 / TE 14 by
  consensus rank, confirmed-unavailable players removed -- see Availability), 2,000 seeded uniform roster draws (2 QB, 5 RB, 5 WR,
  2 TE) shared by every expert, standard 1QB / 2RB / 2WR / 1TE / 1 FLEX lineup. Regret = best-possible
  points minus the expert's lineup. **Edge** = field-average regret minus own (points/week, + is good).
  Regret is also split into QB / RB / WR / TE / FLEX components.
- **Diagnostics:** pairwise start/sit accuracy and points-captured (same-position pairs within 6
  consensus ranks), by position and consensus tier (T1 1-6, T2 7-12, T3 13-24, T4 25+); rank correlation;
  coverage / imputed counts / pool players with no result row (`pool_unmatched`).
- **Units:** NFL weeks are the independent observations. Roster scenarios only reduce noise within a week.
- Half-PPR and full-PPR are scored separately. A source that ranks < 50% of the pool is treated as absent
  that week (no update, uncertainty grows). Unranked pool players are imputed at the expert's own max rank + 1.

## Weights (shadow)

Per expert, a local-level Kalman filter on the weekly edge (prior sd 0.5 pts/wk, drift 0.01/wk, extra 0.10
variance at each season boundary, weekly noise estimated as-of from the pooled data). Weights =
softmax(skill) tilt on equal weights, clipped to 0.5x-1.8x an equal share, rate-limited to 0.18/K per
week. Weights for week t use only weeks < t. `six` = all six experts; `three` = Draft Sharks/Boone/Smyth
(skills are always estimated against the full field). Settings live in `config.py` (`SPEC`, versioned)
and are placeholders to be revisited with more data.

## Storage (Supabase authoritative; CSV mirror in `~/FantasyData/in-season/expert_eval/`)

`expert_eval_config`, `_results`, `_snapshots`, `_pool`, `_scores` (tall: position/tier = `ALL` for
overall rows), `_weights`, `_backtests`, `_runs`. Migration `supabase/migrations/0004_expert_eval.sql`
(additive). Every write is an upsert on a natural key; reruns are idempotent (verified: identical scores
across reruns) and nothing is deleted. A rerun after nflverse stat corrections updates that week in place.

## Promotion gate (`promotion.py`, `--backtest`)

**Primary benchmark = the site's current static weights** (`STATIC_WEIGHTS`, the incumbent); equal weighting is a
secondary, reported-only benchmark. A candidate must clear every check in BOTH scoring formats: mean saved vs static
>= 0.10 pts/wk, week-bootstrap P(improve) >= 0.70, share of weeks worse <= 55%, worst week >= -4, average turnover
<= 0.08, and (once the other checks pass) an exact permutation test p <= 0.10. Thresholds live in `config.SPEC["gate"]`.

Strategies are fixed in advance, not tuned: `static3` (incumbent), `equal3/equal6`, `dyn3/dyn6` (shadow Kalman
weights, as-is), `anchor10/20/30` (incumbent + extra experts at a fixed dose), `plus_<expert>` (incumbent + one extra at
15%), and two pre-declared CANDIDATES -- `anchor20dyn` (incumbent 80% + extras 20% split by learned skill) and
`blend50` (50% learned six-expert + 50% incumbent). Only candidates can be promoted; the rest are diagnostics, so
multiple-comparison exposure is two candidates.

Result (2026 weeks 2-9, and 2025 archive weeks 2-18 as sensitivity): no candidate beats the incumbent in either
format; adding extra experts at any dose is flat to negative, learned weights do not beat static. Single-expert
diagnostics (e.g. Winks +0.26 in half-PPR only) are not acted on. Live Rankings stay on the static three-expert weights.

## Availability (config v1.1)

Players with no stats are classified from nflverse weekly rosters + injury reports (`results.py`):
`inactive_roster` (game-day inactive INA, IR/RES, cut, practice squad), `out_report` (final report Out),
`doubtful_dnp` / `questionable_dnp` (active on the roster, no stats), and `no_result` (none of the above:
unexpected scratch or a name-match gap; scored 0 and counted). Policy `all_confirmed` (default) removes
the first two from every expert's lineup choices; Doubtful/Questionable sitters stay eligible at 0.
Counts per week are stored as `pool_*` metrics; `top_unavailable` keeps each expert's late-news exposure visible; and
`rw_regret` / `rw_edge` score the same experts on a pool that does NOT remove late inactives (they score 0), i.e. real-world
lineups without hindsight (pool version `v1.1-rw`). Sensitivity (`--audit`): `known_early` gives the same expert ordering; `none` (score
every non-player as 0) reorders the experts (Draft Sharks drops from +1.1 to -0.6 pts/wk), so that
choice matters and is labeled in the config.

## Audit and integrity

`--audit`: (1) leakage -- weights for week t are unchanged when all weeks >= t are replaced with noise;
(2) exact permutation test -- all 720 re-assignments of the learned skills to experts, to see how often a
weights path unrelated to real skill matches the real gain; (3) leave-one-week-out and refit-without-week;
(4) inactive-policy sensitivity. The backtest gate includes the permutation check for the six-expert
strategy (`gate.max_perm_p`). `audit.verify_integrity` checks that half/full-PPR weights derive only from
their own format's edges and that a full rerun leaves snapshots, pools, results, scores and older config
versions unchanged.

## Preservation rules

Snapshots and pools are insert-only (a stored week is reused, never reselected). Results are upserted
(nflverse stat corrections); the number of changed rows is logged per run (`expert_eval_runs.notes`).
Scores/weights are upserts on natural keys under a config version; a methodology change is a new version,
and older versions stay in the tables. A run evaluates new weeks plus the latest two (`RECHECK_WEEKS`).

## Operations

`scheduled_pull.ps1` runs `run_expert_eval.py` after the Supabase push. It never fails the pull; on
failure it writes `data/last_expert_eval_status.json` (`ok:false`, error) and emails once per day.
Weeks are evaluated only after every game is final (last kickoff + 5h).

## Historical archive (Yahoo 2023-2025)

`archive.py` (`run_archive`). Yahoo returns past weeks on demand but without pull times, so these ranks are labeled
`provenance='yahoo_archive'`, use config_version `v1.1-archive`, and are never mixed into the live series. 2025 (weeks
1-18; Boone, Harmon, Pianowski, Smyth through week 16; no Draft Sharks or Winks) is backfilled for exploratory analysis and
sensitivity testing only -- no weights are written and nothing trains production weights from it.
Probe (2026, weeks 7-9): the endpoint queried after the games matches the frozen pre-kickoff snapshot
exactly for only 54-67% of players (mean absolute difference 1.2-5.0 ranks), so the archive is NOT
guaranteed to be the lock-time ranking. Its correlation with results (0.3-0.7 by position) is in the
normal forecast range, so there is no sign of results leaking into the ranks.

## Known limits / TODO

- Position/tier weights, points-space blending, ownership-weighted rosters: future.
