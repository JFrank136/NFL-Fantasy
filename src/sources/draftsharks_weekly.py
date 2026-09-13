"""Draft Sharks weekly rankings -- public, unauthenticated `load-rows` endpoint.

See docs/DATA.md for the verified request/response shape. Unlike Draft/'s
draft-day CSV export, this needs no login and no Playwright -- it's a plain
HTML-fragment endpoint reachable with `requests`.
"""

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.draftsharks.com/weekly-rankings/load-rows"
PAGE_SIZE = 300
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"


class DraftSharksFetchError(RuntimeError):
    pass


@dataclass
class DraftSharksRow:
    source_player_id: str
    player_name: str
    team: str | None
    position: str
    rank: int | None
    matchup: str | None
    strength_of_schedule: str | None
    bye: int | None
    floor_proj: float | None
    consensus_proj: float | None
    ds_proj: float | None
    ceiling_proj: float | None
    three_d_proj: float | None
    tier_overall: int | None
    tier_positional: int | None
    is_rookie: bool


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_page(html: str) -> list[DraftSharksRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[DraftSharksRow] = []
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

        rows.append(DraftSharksRow(
            source_player_id=tbody.get("data-key", ""),
            player_name=tbody.get("data-player-name", "").strip(),
            team=team,
            position=tbody.get("data-fantasy-position", ""),
            rank=_to_int(rank_span.get_text(strip=True)) if rank_span else None,
            matchup=cells.get("matchup") or None,
            strength_of_schedule=cells.get("strength_of_schedule") or None,
            bye=_to_int(cells.get("player.team.bye")),
            floor_proj=_to_float(cells.get("weeklyFloorPts")),
            consensus_proj=_to_float(cells.get("consensus_projection")),
            ds_proj=_to_float(cells.get("weeklyPts")),
            ceiling_proj=_to_float(cells.get("weeklyCeilingPts")),
            three_d_proj=_to_float(cells.get("weekly3dPts")),
            tier_overall=_to_int(tbody.get("data-tier-overall")),
            tier_positional=_to_int(tbody.get("data-tier-positional")),
            is_rookie=(tbody.get("data-is-rookie") == "true"),
        ))
    return rows


def fetch_draftsharks_weekly(
    week: int,
    scoring_slug: str,
    position: str = "",
    request_delay: float = 0.5,
    session: requests.Session | None = None,
) -> list[DraftSharksRow]:
    """Fetches every ranked player for one week/scoring combo, paginating
    with `offset` until a page returns zero rows. `scoring_slug` is Draft
    Sharks' own URL slug -- confirmed values are "ppr" and "half-ppr"."""
    sess = session or requests.Session()
    all_rows: list[DraftSharksRow] = []
    offset = 0
    while True:
        params = {
            "offset": offset,
            "limit": PAGE_SIZE,
            "fantasyPosition": position,
            "pprSuperflexSlug": scoring_slug,
            "sort": "-weekly3dPts",
            "week": week,
            "researchDepth": "rankings",
        }
        try:
            response = sess.get(
                BASE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DraftSharksFetchError(
                f"Draft Sharks load-rows request failed at offset={offset}: {exc}"
            ) from exc

        page_rows = _parse_page(response.text)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        offset += len(page_rows)
        if len(page_rows) < PAGE_SIZE:
            break
        time.sleep(request_delay)

    return all_rows
