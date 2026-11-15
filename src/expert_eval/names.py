"""Name/team normalization for evaluation joins. Raw ranking history is never
rewritten: every join here re-derives its key from the raw player name."""
from src.player_identity import canonical_name_for

TEAM_MAP = {"LVR": "LV", "LAR": "LA", "JAC": "JAX", "WSH": "WAS", "ARZ": "ARI", "BLT": "BAL",
            "CLV": "CLE", "HST": "HOU", "SD": "LAC", "OAK": "LV", "STL": "LA"}
OFFENSE = ("QB", "RB", "WR", "TE")


def canon(raw_name) -> str:
    if raw_name is None or raw_name != raw_name:
        return ""
    return canonical_name_for(str(raw_name)).strip().lower()


def norm_team(team):
    if team is None or team != team:
        return None
    t = str(team).strip().upper()
    return TEAM_MAP.get(t, t)


def scale_group(position: str) -> str:
    """Rank scale a position lives on: QBs against QBs, RB/WR/TE share the FLEX scale."""
    return "QB" if position == "QB" else "FLEX"
