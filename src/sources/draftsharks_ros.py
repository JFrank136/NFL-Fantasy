"""Draft Sharks rest-of-season (ROS) rankings -- public, unauthenticated
`load-rows` endpoint, same family as weekly-rankings/load-rows
(draftsharks_weekly.py) but a different report: `dsValue` is Draft Sharks'
single blended ROS trade value (their "3D value" score, analogous to
weekly's `weekly3dPts`), and the row shape carries floor/ceiling ROS
projections, games-played-rest-of-season, and injury risk instead of a
single week's matchup/opponent.

Unlike weekly rankings (one `fantasyPosition` per call), this endpoint
returns every position -- offense and IDP/K/DEF -- in one paginated call
per scoring slug when `fantasyPosition` is left blank. This project only
tracks QB/RB/WR/TE, so `fetch_draftsharks_ros` filters non-fantasy
positions out before returning.

See docs/DATA.md for the verified request/response shape.
"""

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.draftsharks.com/ros-rankings/load-rows"
PAGE_SIZE = 300
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


class DraftSharksRosFetchError(RuntimeError):
    pass


@dataclass
class DraftSharksRosRow:
    source_player_id: str
    player_name: str
    team: str | None
    position: str
    rank: int | None
    tier_overall: int | None
    tier_positional: int | None
    strength_of_schedule: str | None
    bye: int | None
    games_played: int | None
    floor_proj: float | None       # rosWeeklyFloorPts
    projection: float | None        # rosWeeklyPts
    ceiling_proj: float | None      # rosWeeklyCeilingPts
    ds_value: float | None          # dsValue -- Draft Sharks' blended ROS trade value
    injury_risk: str | None         # player.sipPlayerProfile.injury_prob, raw/unparsed


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        # Confirmed live 2026-09-17: games_played's data-value renders as a
        # float string ("16.0"), not a plain int ("16") like the other
        # int-typed fields -- fall back to a float parse before giving up.
        try:
            return int(float(value))
        except ValueError:
            return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_page(html: str) -> list[DraftSharksRosRow]:
    """Parses every `tbody[data-player-row]` block on the page, including
    non-fantasy positions (LB/DL/DB/K/DEF) -- filtering to QB/RB/WR/TE is
    `fetch_draftsharks_ros`'s job, not this function's, so pagination math
    (which depends on the RAW page row count) stays correct."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[DraftSharksRosRow] = []
    for tbody in soup.select("tbody[data-player-row]"):
        cells = {
            td["data-attribute"]: td.get("data-value")
            for td in tbody.select("td[data-attribute]")
        }
        rank_span = tbody.select_one(".rank-index span")
        team_img = tbody.select_one("img.team-badge")
        team = None
        if team_img and team_img.get("src"):
            match = re.search(r"/teams/([A-Z]+)\.svg", team_img["src"])
            if match:
                team = match.group(1)

        rows.append(DraftSharksRosRow(
            source_player_id=tbody.get("data-key", ""),
            player_name=tbody.get("data-player-name", "").strip(),
            team=team,
            position=tbody.get("data-fantasy-position", ""),
            rank=_to_int(rank_span.get_text(strip=True)) if rank_span else None,
            tier_overall=_to_int(tbody.get("data-tier-overall")),
            tier_positional=_to_int(tbody.get("data-tier-positional")),
            strength_of_schedule=cells.get("strength_of_schedule") or None,
            bye=_to_int(cells.get("player.team.bye")),
            games_played=_to_int(cells.get("games_played")),
            floor_proj=_to_float(cells.get("rosWeeklyFloorPts")),
            projection=_to_float(cells.get("rosWeeklyPts")),
            ceiling_proj=_to_float(cells.get("rosWeeklyCeilingPts")),
            ds_value=_to_float(cells.get("dsValue")),
            injury_risk=cells.get("player.sipPlayerProfile.injury_prob") or None,
        ))
    return rows


def fetch_draftsharks_ros(
    scoring_slug: str,
    request_delay: float = 0.5,
    session: requests.Session | None = None,
) -> list[DraftSharksRosRow]:
    """Fetches every QB/RB/WR/TE player's ROS rankings for one scoring
    format, paginating with `offset` until a page returns zero rows (same
    pattern as fetch_draftsharks_weekly), then filtering out non-fantasy
    positions (LB/DL/DB/K/DEF) before returning."""
    sess = session or requests.Session()
    all_rows: list[DraftSharksRosRow] = []
    offset = 0
    while True:
        params = {
            "offset": offset,
            "limit": PAGE_SIZE,
            "fantasyPosition": "",
            "pprSuperflexSlug": scoring_slug,
            "sort": "-dsValue",
            "researchDepth": "rankings",
        }
        try:
            response = sess.get(
                BASE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DraftSharksRosFetchError(
                f"Draft Sharks ROS load-rows request failed at offset={offset}: {exc}"
            ) from exc

        page_rows = _parse_page(response.text)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        offset += len(page_rows)
        if len(page_rows) < PAGE_SIZE:
            break
        time.sleep(request_delay)

    return [r for r in all_rows if r.position in FANTASY_POSITIONS]
