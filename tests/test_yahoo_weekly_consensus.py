"""Parsing test against a real captured response from
sports.yahoo.com/api/fanPro/ (2026-09-08, week 1, QB, HALF), trimmed to two
players -- shape otherwise unmodified."""

import pytest
import requests

from src.sources.yahoo_weekly_consensus import (
    YahooConsensusFetchError,
    _expert_id_by_name,
    _fetch_position,
    fetch_expert_weekly,
)

REAL_RESPONSE = {
    "players": [
        {
            "id": "17233", "name": "Lamar Jackson", "shortName": "L. Jackson",
            "position": "QB", "playerYahooId": "31002", "team": "BAL", "rank": 1,
            "tier": 0, "consensusRank": "1.40", "expertCount": 5, "adp": 0,
            "byeWeek": 13, "opponent": "at IND", "percentOwned": 100,
            "experts": {"9": "1", "317": "3", "747": "1", "7604": "1", "7666": "1"},
        },
        {
            "id": "19275", "name": "Jalen Hurts", "shortName": "J. Hurts",
            "position": "QB", "playerYahooId": "32723", "team": "PHI", "rank": 2,
            "tier": 0, "consensusRank": "2.60", "expertCount": 5, "adp": 0,
            "byeWeek": 10, "opponent": "vs. WAS", "percentOwned": 100,
            "experts": {"9": "3", "317": "2", "747": "3", "7604": "2", "7666": "3"},
        },
    ],
    "lastUpdated": "2026-09-09T01:38:03.466Z",
    "week": "1",
    "season": 2026,
    "expertNames": {
        "9": "Scott Pianowski", "317": "Justin Boone", "747": "Matt Harmon",
        "7604": "Joel Smyth", "7666": "Hayden Winks",
    },
    "expertPubDates": {
        "9": "2026-09-08 16:24:32", "317": "2026-09-08 11:51:43",
        "747": "2026-09-08 13:52:10", "7604": "2026-09-08 16:44:29",
        "7666": "2026-09-08 21:13:34",
    },
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        return FakeResponse(self._payload)


def test_expert_id_by_name():
    assert _expert_id_by_name(REAL_RESPONSE["expertNames"], "Justin Boone") == "317"
    assert _expert_id_by_name(REAL_RESPONSE["expertNames"], "Joel Smyth") == "7604"
    assert _expert_id_by_name(REAL_RESPONSE["expertNames"], "Nobody") is None


def test_boone_and_smyth_get_different_ranks_from_same_response():
    session = FakeSession(REAL_RESPONSE)
    boone_rows = fetch_expert_weekly(
        "Justin Boone", week=1, year=2026, scoring_slug="half-ppr",
        positions=["QB"], request_delay=0, session=session,
    )
    smyth_rows = fetch_expert_weekly(
        "Joel Smyth", week=1, year=2026, scoring_slug="half-ppr",
        positions=["QB"], request_delay=0, session=session,
    )
    boone_ranks = {r.player_name: r.rank for r in boone_rows}
    smyth_ranks = {r.player_name: r.rank for r in smyth_rows}
    assert boone_ranks == {"Lamar Jackson": 3, "Jalen Hurts": 2}
    assert smyth_ranks == {"Lamar Jackson": 1, "Jalen Hurts": 2}


def test_unknown_expert_raises():
    session = FakeSession(REAL_RESPONSE)
    with pytest.raises(YahooConsensusFetchError):
        fetch_expert_weekly(
            "Not A Real Analyst", week=1, year=2026, scoring_slug="half-ppr",
            positions=["QB"], request_delay=0, session=session,
        )


def test_invalid_scoring_slug_raises():
    session = FakeSession(REAL_RESPONSE)
    with pytest.raises(YahooConsensusFetchError):
        fetch_expert_weekly(
            "Justin Boone", week=1, year=2026, scoring_slug="standard",
            positions=["QB"], request_delay=0, session=session,
        )


def test_missing_keys_in_response_raises():
    session = FakeSession({"error": "Failed to fetch fantasy rankings"})
    with pytest.raises(YahooConsensusFetchError):
        _fetch_position("QB", week=1, year=2026, scoring_slug="half-ppr", session=session)
