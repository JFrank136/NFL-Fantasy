"""Freeze each expert's last pre-kickoff ranking per player, on the same
QB / FLEX scales the site blends on."""
import pandas as pd

from src.expert_eval.names import scale_group


def select_snapshots(rankings: pd.DataFrame, sched: pd.DataFrame, max_age_days: float = 8) -> pd.DataFrame:
    """For every (week, source, scoring, player) keep the latest pull strictly before that
    player's own team kickoff and no more than `max_age_days` old (a stale pull from before
    a source dropped a player is treated as unranked, not as a current opinion). Rows for
    teams missing from the schedule fall back to the week's earliest kickoff (conservative:
    never uses a pull that could postdate a game)."""
    r = rankings.merge(sched.rename(columns={"ko": "kickoff_at"}), on=["week", "team"], how="left")
    earliest = sched.groupby("week").ko.min()
    r["kickoff_at"] = r.kickoff_at.fillna(r.week.map(earliest))
    r = r[(r.pulled_at < r.kickoff_at) & (r.pulled_at >= r.kickoff_at - pd.Timedelta(days=max_age_days))]
    r = r.sort_values("pulled_at")
    r = r.groupby(["week", "source", "scoring", "canon", "position"], as_index=False).tail(1)
    r = r.rename(columns={"rank": "raw_rank"}).dropna(subset=["raw_rank"])
    r["scaled_rank"] = scaled_ranks(r)
    r["provenance"] = "pipeline"
    return r[["week", "source", "scoring", "canon", "position", "raw_rank", "scaled_rank",
              "pulled_at", "kickoff_at", "provenance"]].reset_index(drop=True)


def scaled_ranks(df: pd.DataFrame) -> pd.Series:
    """Mirror of site rescaleDraftSharksRanks: Draft Sharks publishes one overall rank
    (IDP/K/DST included), so it is re-ranked within QB / FLEX (RB,WR,TE) with competition
    ranking. Yahoo experts already rank on those scales and are used as published."""
    out = df.raw_rank.astype(float).copy()
    ds = df.source == "draftsharks"
    if ds.any():
        grp = df.position.map(scale_group)
        out[ds] = df[ds].groupby(["week", "scoring", grp[ds]]).raw_rank.rank(method="min")
    return out
