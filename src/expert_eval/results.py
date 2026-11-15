"""Actual fantasy results per player-week, plus pre-kickoff inactive status."""
import pandas as pd

from src.expert_eval.inputs import load_injuries, load_player_stats
from src.expert_eval.names import canon, OFFENSE


def build_results(season: int) -> pd.DataFrame:
    ps = load_player_stats(season)
    ps = ps[ps.position.isin(OFFENSE)].copy()
    ps["canon"] = ps.player_display_name.map(canon)
    ps["pts_std"] = ps.fantasy_points
    ps["pts_ppr"] = ps.fantasy_points_ppr
    res = ps.groupby(["week", "canon", "position"], as_index=False).agg(
        team=("team", "last"), pts_std=("pts_std", "sum"), pts_ppr=("pts_ppr", "sum"))
    res["pts_half"] = (res.pts_std + res.pts_ppr) / 2
    res["played"] = True
    res["inactive"] = False

    inj = load_injuries(season)
    inj = inj[(inj.report_status == "Out") & inj.position.isin(OFFENSE) & inj.full_name.notna()].copy()
    inj["canon"] = inj.full_name.map(canon)
    out = inj[["week", "canon", "position", "team"]].drop_duplicates(["week", "canon", "position"])
    out = out.merge(res[["week", "canon", "position"]], how="left", indicator=True)
    out = out[out._merge == "left_only"].drop(columns="_merge")
    for c in ("pts_std", "pts_half", "pts_ppr"):
        out[c] = 0.0
    out["played"] = False
    out["inactive"] = True
    return pd.concat([res, out], ignore_index=True)
