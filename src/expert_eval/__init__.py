"""Expert accuracy evaluation and (shadow) dynamic weighting.

Pipeline: ranking history + nflverse results -> frozen pre-kickoff snapshots ->
weekly lineup-regret evaluation per expert -> shadow weights -> walk-forward
backtest. Nothing here changes the live Rankings page; see docs/EXPERT_EVAL.md.
"""
