"""Raw inputs: the append-only rankings history (read-only) and nflverse
schedule/results/injuries."""
from datetime import datetime, timezone

import pandas as pd

from src import paths
from src.expert_eval.names import canon, norm_team, OFFENSE

RANKINGS_CSV = paths.PROCESSED_DIR / "rankings_long.csv"
_USECOLS = ["season", "week", "source", "scoring", "pulled_at", "player_name", "team", "position", "rank"]


def load_rankings(season: int, weeks=None, scoring=None, path=RANKINGS_CSV) -> pd.DataFrame:
    """Offense-only ranking rows for a season. Keys are re-derived from the raw
    player name (canon) so historical name inconsistencies never need a data fix."""
    parts = []
    for chunk in pd.read_csv(path, usecols=_USECOLS, chunksize=400_000, low_memory=False):
        chunk = chunk[(chunk.season == season) & chunk.position.isin(OFFENSE)]
        if weeks is not None:
            chunk = chunk[chunk.week.isin(list(weeks))]
        if scoring is not None:
            chunk = chunk[chunk.scoring == scoring]
        if len(chunk):
            parts.append(chunk)
    if not parts:
        return pd.DataFrame(columns=_USECOLS + ["canon"])
    df = pd.concat(parts, ignore_index=True)
    df["pulled_at"] = pd.to_datetime(df.pulled_at, utc=True)
    df["team"] = df.team.map(norm_team)
    names = {n: canon(n) for n in df.player_name.dropna().unique()}
    df["canon"] = df.player_name.map(names)
    return df[df.canon != ""]


def load_schedule(season: int) -> pd.DataFrame:
    """One row per (week, team) with the team's kickoff in UTC."""
    import nflreadpy
    sc = nflreadpy.load_schedules([season]).to_pandas()
    sc = sc[sc.game_type == "REG"] if "game_type" in sc else sc
    sc["ko"] = pd.to_datetime(sc.gameday + " " + sc.gametime).dt.tz_localize(
        "America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    home = sc[["week", "home_team", "ko"]].rename(columns={"home_team": "team"})
    away = sc[["week", "away_team", "ko"]].rename(columns={"away_team": "team"})
    g = pd.concat([home, away], ignore_index=True)
    g["team"] = g.team.map(norm_team)
    return g.dropna(subset=["ko"])


def week_is_final(sched: pd.DataFrame, week: int, now=None, buffer_hours=5) -> bool:
    """True once the week's last kickoff is far enough behind us that every game is over."""
    now = now or datetime.now(timezone.utc)
    ks = sched[sched.week == week].ko
    return len(ks) > 0 and now > ks.max() + pd.Timedelta(hours=buffer_hours)


def load_player_stats(season: int) -> pd.DataFrame:
    import nflreadpy
    ps = nflreadpy.load_player_stats([season]).to_pandas()
    return ps[(ps.season_type == "REG") & ps.player_display_name.notna()]


def load_injuries(season: int) -> pd.DataFrame:
    import nflreadpy
    return nflreadpy.load_injuries([season]).to_pandas()


def load_rosters_weekly(season: int) -> pd.DataFrame:
    import nflreadpy
    r = nflreadpy.load_rosters_weekly([season]).to_pandas()
    return r[(r.game_type == "REG") & r.position.isin(OFFENSE) & r.full_name.notna()]
