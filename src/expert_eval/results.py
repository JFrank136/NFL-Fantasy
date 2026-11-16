"""Actual fantasy results per player-week, plus a pre-kickoff availability status.

Statuses for players who did NOT record stats that week (precedence top to bottom):
  inactive_roster  weekly roster status INA/RES/CUT/EXE/RET/DEV -- the game-day inactive list /
                   IR; known before kickoff, so confirmed-unavailable (excluded from lineup choices)
  out_report       final injury report says Out (confirmed-unavailable)
  doubtful_dnp     Doubtful, active on the roster, no stats (a real, avoidable-in-hindsight risk)
  questionable_dnp Questionable, active, no stats (game-time decision that went the wrong way)
Players with no stats row and none of the above are simply absent here; evaluation labels
them 'no_result' (unexpected inactive / healthy scratch / name-match gap) and scores them 0.
Which statuses count as confirmed-unavailable is a config choice (SPEC['inactive_statuses'])."""
import pandas as pd

from src.expert_eval.inputs import load_injuries, load_player_stats, load_rosters_weekly
from src.expert_eval.names import canon, OFFENSE

ROSTER_UNAVAILABLE = {"INA", "RES", "CUT", "EXE", "RET", "DEV"}
CONFIRMED = ("inactive_roster", "out_report")


def build_results(season: int) -> pd.DataFrame:
    ps = load_player_stats(season)
    ps = ps[ps.position.isin(OFFENSE)].copy()
    ps["canon"] = ps.player_display_name.map(canon)
    res = ps.groupby(["week", "canon", "position"], as_index=False).agg(
        team=("team", "last"), pts_std=("fantasy_points", "sum"), pts_ppr=("fantasy_points_ppr", "sum"))
    res["pts_half"] = (res.pts_std + res.pts_ppr) / 2
    res["played"] = True
    res["status"] = "played"
    res["roster_status"] = None
    res["report_status"] = None

    played = set(zip(res.week, res.canon))
    ros = load_rosters_weekly(season).copy()
    ros["canon"] = ros.full_name.map(canon)
    ros = ros[[(w, c) not in played for w, c in zip(ros.week, ros.canon)]]
    unavailable = ros[ros.status.isin(ROSTER_UNAVAILABLE)][["week", "canon", "position", "team"]].assign(status="inactive_roster")
    active_dnp = ros[~ros.status.isin(ROSTER_UNAVAILABLE)][["week", "canon", "position", "team"]]

    inj = load_injuries(season)
    inj = inj[inj.position.isin(OFFENSE) & inj.full_name.notna()].copy()
    inj["canon"] = inj.full_name.map(canon)
    inj_all = inj
    inj = inj[[(w, c) not in played for w, c in zip(inj.week, inj.canon)]].copy()
    kind = {"Out": "out_report", "Doubtful": "doubtful_dnp", "Questionable": "questionable_dnp"}
    inj["status"] = inj.report_status.map(kind)
    inj = inj.dropna(subset=["status"])[["week", "canon", "position", "team", "status"]]
    # Doubtful/Questionable only count as "sat" when the roster says they were active.
    soft = inj[inj.status.isin(["doubtful_dnp", "questionable_dnp"])]
    soft = soft.merge(active_dnp[["week", "canon"]].drop_duplicates(), on=["week", "canon"], how="inner")
    hard = inj[inj.status == "out_report"]

    extra = pd.concat([unavailable, hard, soft], ignore_index=True)
    rank = {"inactive_roster": 0, "out_report": 1, "doubtful_dnp": 2, "questionable_dnp": 3}
    extra = extra.sort_values("status", key=lambda s: s.map(rank)).drop_duplicates(["week", "canon"], keep="first")
    rs = ros[["week", "canon", "status"]].drop_duplicates(["week", "canon"]).rename(columns={"status": "roster_status"})
    rp = inj_all[["week", "canon", "report_status"]].drop_duplicates(["week", "canon"])
    extra = extra.merge(rs, on=["week", "canon"], how="left").merge(rp, on=["week", "canon"], how="left")
    for c in ("pts_std", "pts_half", "pts_ppr"):
        extra[c] = 0.0
    extra["played"] = False
    out = pd.concat([res, extra], ignore_index=True)
    out["inactive"] = out.status.isin(CONFIRMED)
    return out
