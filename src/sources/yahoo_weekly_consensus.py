"""Boone and Smyth's weekly rankings, via Yahoo's own `api/fanPro/` endpoint --
the same public, unauthenticated endpoint `Draft/src/sources/yahoo_consensus.py`
already uses for the draft-day board, extended here with `week` (confirmed to
work for week > 0, not just the draft-day week=0) and per-position calls (this
project's positions of interest, not all of Yahoo's).

Returns BOTH Boone's and Smyth's individual ranks from a single response per
position -- no separate per-expert request needed, and no guessing at expert
IDs: they're resolved by name from the response's own `expertNames` map, same
safety property as the draft-day module.
"""

import time
from dataclasses import dataclass

import requests

BASE_URL = "https://sports.yahoo.com/api/fanPro/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"]
SCORING_MAP = {"half-ppr": "HALF", "ppr": "PPR"}

# All 5 of Yahoo's current fantasy analysts -- required in `filters` for the
# endpoint to return any experts= data at all (confirmed live: omitting an
# expert from `filters` omits them from every player's `experts` map).
FILTER_EXPERT_IDS = "9:317:747:7604:7666"


class YahooConsensusFetchError(RuntimeError):
    pass


@dataclass
class ExpertWeeklyRow:
    source_player_id: str
    player_name: str
    team: str | None
    position: str
    rank: int | None  # this expert's own rank, not the blended consensusRank
    bye: int | None
    opponent: str | None


def _fetch_position(
    position: str, week: int, year: int, scoring_slug: str, session: requests.Session
) -> dict:
    if scoring_slug not in SCORING_MAP:
        raise YahooConsensusFetchError(
            f"Unrecognized scoring_slug {scoring_slug!r} -- only "
            f"{list(SCORING_MAP)} are confirmed against this endpoint."
        )
    params = {
        "sport": "NFL",
        "position": position,
        "filters": FILTER_EXPERT_IDS,
        "experts": "show",
        "expert": "7261",
        "scoring": SCORING_MAP[scoring_slug],
        "type": "ST",
        "week": week,
        "wtype": "ST",
        "year": year,
    }
    try:
        response = session.get(
            BASE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise YahooConsensusFetchError(
            f"Yahoo fanPro request failed for position={position} week={week}: {exc}"
        ) from exc
    except ValueError as exc:
        raise YahooConsensusFetchError(
            f"Yahoo fanPro returned non-JSON for position={position} week={week}: {exc}"
        ) from exc

    if "expertNames" not in data or "players" not in data:
        raise YahooConsensusFetchError(
            f"Unexpected Yahoo fanPro response shape for position={position} "
            f"week={week} -- expected 'expertNames' and 'players', got: "
            f"{list(data.keys())}"
        )
    return data


def _expert_id_by_name(expert_names: dict, name: str) -> str | None:
    return next((eid for eid, n in expert_names.items() if n == name), None)


def fetch_expert_weekly(
    expert_name: str,
    week: int,
    year: int,
    scoring_slug: str,
    positions: list[str] | None = None,
    request_delay: float = 0.5,
    session: requests.Session | None = None,
) -> list[ExpertWeeklyRow]:
    """Fetches one named expert's (e.g. "Justin Boone", "Joel Smyth")
    individual weekly ranks across positions, looking up their expert id by
    name each call rather than trusting a hardcoded id -- if Yahoo reassigns
    ids, only `expert_name` needs to keep matching, not a code change."""
    sess = session or requests.Session()
    rows: list[ExpertWeeklyRow] = []
    for position in (positions or POSITIONS):
        data = _fetch_position(position, week, year, scoring_slug, sess)
        expert_id = _expert_id_by_name(data["expertNames"], expert_name)
        if expert_id is None:
            raise YahooConsensusFetchError(
                f"Could not find expert {expert_name!r} in Yahoo's expertNames "
                f"map for position={position} week={week}: {data['expertNames']}"
            )
        for player in data["players"]:
            experts = player.get("experts", {})
            if expert_id not in experts:
                continue  # this expert hasn't ranked this player -- not an error
            rows.append(ExpertWeeklyRow(
                source_player_id=str(player.get("id", "")),
                player_name=player.get("name", "").strip(),
                team=player.get("team"),
                position=player.get("position", position),
                rank=int(experts[expert_id]),
                bye=player.get("byeWeek"),
                opponent=player.get("opponent"),
            ))
        time.sleep(request_delay)
    return rows
