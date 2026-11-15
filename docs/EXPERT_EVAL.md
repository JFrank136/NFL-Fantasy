# Expert accuracy evaluation and shadow weighting

Code: `src/expert_eval/`. CLI: `scripts/run_expert_eval.py` (`--backtest` for the walk-forward test,
`--local-only` for a Supabase-free dry run). Standalone weekly wrapper: `scripts/run_expert_eval.ps1`
(not wired into `scheduled_pull.ps1`). Site page: **Expert Accuracy**. Tests: `tests/test_expert_eval.py`,
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
  consensus rank, confirmed-Out players removed), 2,000 seeded uniform roster draws (2 QB, 5 RB, 5 WR,
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

## Backtest and promotion gate

`--backtest` replays each season week by week: dynamic (six / three, separate / pooled across scoring)
vs equal weights vs the site's static weights vs individual experts, on identical pools and scenarios.
Gate thresholds (config `gate`): mean improvement >= 0.10 pts/wk, week-bootstrap P(improve) >= 0.70,
share of weeks worse <= 55%, worst week >= -4, average turnover <= 0.08. Early (single-season) results are
indicative only.

## Known limits / TODO

- "Confirmed inactive" = final injury report "Out". Questionable/Doubtful players who sat score 0.
- Weekly history before 2026: Yahoo's `fanPro` endpoint returns 2025 weekly ranks for Boone, Smyth,
  Harmon and Pianowski (and 2023-2024 for Pianowski/Harmon); Draft Sharks and Winks history not found.
  Not backfilled yet (no pull timestamps, so "pre-kickoff" cannot be verified for those).
- Position/tier weights, points-space blending, ownership-weighted rosters: future.
