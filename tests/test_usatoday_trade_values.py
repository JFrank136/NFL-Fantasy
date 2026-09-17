"""USA Today trade-value discovery/parser tests using captured HTML shapes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import requests

from src.sources.usatoday_trade_values import (
    HUB_URL,
    UsaTodayTradeValueFetchError,
    discover_article_url,
    fetch_trade_chart,
)

ARTICLE_URL = (
    "https://fantasy.usatoday.com/story/sports/fantasy/football/2026/09/15/"
    "fantasy-football-trade-value-chart-week-2-ros-rankings/91770884007/"
)

HUB_HTML = f"""
<html><body>
<a href="https://example.com/fantasy-football-trade-value-chart-week-2-ros-rankings/">Wrong host</a>
<a href="https://fantasy.usatoday.com/story/sports/fantasy/football/2025/09/16/fantasy-football-trade-value-chart-week-2-ros-rankings/11111111111/">Old season</a>
<a href="{ARTICLE_URL}">Current week</a>
<a href="https://fantasy.usatoday.com/story/sports/fantasy/football/2026/09/22/fantasy-football-trade-value-chart-week-3-ros-rankings/92222222222/">Week 3</a>
</body></html>
"""

WRONG_HOST_ONLY_HTML = """
<html><body>
<a href="https://example.com/fantasy-football-trade-value-chart-week-2-ros-rankings/">Wrong host</a>
</body></html>
"""

ARTICLE_HTML = """
<html><body>
<h2>Quarterback trade value chart</h2>
<table><thead><tr><th>RK</th><th>Player</th><th>1QB</th><th>6/TD</th><th>SFLEX</th></tr></thead>
<tbody>
<tr><td>1</td><td>Josh Allen</td><td>36</td><td>42</td><td>69</td></tr>
<tr><td>2</td><td>Lamar Jackson</td><td>28</td><td>34</td><td>58</td></tr>
</tbody></table>

<h2>Running back trade value chart</h2>
<table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>PPR</th></tr></thead>
<tbody>
<tr><td>1</td><td>Jahmyr Gibbs</td><td>70</td><td>72</td><td>75</td></tr>
<tr><td>2</td><td>Bijan Robinson</td><td>68</td><td>70</td><td>73</td></tr>
</tbody></table>

<h2>Wide receiver trade value chart</h2>
<table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>Full</th></tr></thead>
<tbody>
<tr><td>1</td><td>Ja'Marr Chase</td><td>64</td><td>65</td><td>67</td></tr>
</tbody></table>

<h2>Tight end trade value chart</h2>
<table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>Full</th></tr></thead>
<tbody>
<tr><td>1</td><td>Brock Bowers</td><td>44</td><td>46</td><td>48</td></tr>
</tbody></table>
</body></html>
"""


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    def __init__(self, text_by_url: dict, raise_for: set[str] = frozenset()):
        self.text_by_url = text_by_url
        self.raise_for = raise_for
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if url in self.raise_for:
            raise requests.ConnectionError("boom")
        return FakeResponse(self.text_by_url[url])


def test_discover_article_url_matches_week_and_season():
    session = FakeSession({HUB_URL: HUB_HTML})
    assert discover_article_url(week=2, season=2026, session=session) == ARTICLE_URL


def test_discover_article_url_ignores_wrong_host():
    session = FakeSession({HUB_URL: WRONG_HOST_ONLY_HTML})
    assert discover_article_url(week=2, season=2026, session=session) is None


def test_discover_article_url_ignores_other_season():
    session = FakeSession({HUB_URL: HUB_HTML})
    assert discover_article_url(week=2, season=2024, session=session) is None


def test_discover_article_url_returns_none_for_unpublished_week():
    session = FakeSession({HUB_URL: HUB_HTML})
    assert discover_article_url(week=99, season=2026, session=session) is None


def test_discover_raises_on_request_failure():
    session = FakeSession({}, raise_for={HUB_URL})
    with pytest.raises(UsaTodayTradeValueFetchError):
        discover_article_url(week=2, season=2026, session=session)


def test_fetch_parses_all_four_position_specific_column_shapes():
    session = FakeSession({ARTICLE_URL: ARTICLE_HTML})
    chart = fetch_trade_chart(ARTICLE_URL, session=session)

    assert list(chart.keys()) == ["QB", "RB", "WR", "TE"]

    qb = chart["QB"][0]
    assert qb.rank == 1
    assert qb.player_name == "Josh Allen"
    assert qb.value_col1_label == "HALF"
    assert qb.value_col1 == 36.0
    assert qb.value_col2_label == "FULL"
    assert qb.value_col2 == 36.0

    rb = chart["RB"][0]
    assert rb.player_name == "Jahmyr Gibbs"
    assert rb.value_col1 == 72.0
    assert rb.value_col2 == 75.0  # RB source header is PPR, not Full.

    wr = chart["WR"][0]
    assert wr.player_name == "Ja'Marr Chase"
    assert wr.value_col1 == 65.0
    assert wr.value_col2 == 67.0

    te = chart["TE"][0]
    assert te.player_name == "Brock Bowers"
    assert te.value_col1 == 46.0
    assert te.value_col2 == 48.0


def test_fetch_position_filter_only_requires_requested_tables():
    rb_only_html = """
    <h2>Running back trade value chart</h2>
    <table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>PPR</th></tr></thead>
    <tbody><tr><td>1</td><td>Jahmyr Gibbs</td><td>70</td><td>72</td><td>75</td></tr></tbody></table>
    """
    session = FakeSession({ARTICLE_URL: rb_only_html})
    chart = fetch_trade_chart(ARTICLE_URL, positions=["RB"], session=session)
    assert list(chart.keys()) == ["RB"]
    assert chart["RB"][0].value_col2 == 75.0


def test_fetch_raises_when_requested_position_table_missing():
    session = FakeSession({ARTICLE_URL: "<p>no trade tables</p>"})
    with pytest.raises(UsaTodayTradeValueFetchError):
        fetch_trade_chart(ARTICLE_URL, positions=["RB"], session=session)


def test_fetch_raises_on_wrong_rb_header_instead_of_silently_losing_full_ppr():
    wrong_rb_html = """
    <h2>Running back trade value chart</h2>
    <table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>Full</th></tr></thead>
    <tbody><tr><td>1</td><td>Jahmyr Gibbs</td><td>70</td><td>72</td><td>75</td></tr></tbody></table>
    """
    session = FakeSession({ARTICLE_URL: wrong_rb_html})
    with pytest.raises(UsaTodayTradeValueFetchError):
        fetch_trade_chart(ARTICLE_URL, positions=["RB"], session=session)


def test_fetch_raises_on_non_numeric_value():
    broken_html = """
    <h2>Wide receiver trade value chart</h2>
    <table><thead><tr><th>RK</th><th>Player</th><th>STD</th><th>Half</th><th>Full</th></tr></thead>
    <tbody><tr><td>1</td><td>Ja'Marr Chase</td><td>64</td><td>oops</td><td>67</td></tr></tbody></table>
    """
    session = FakeSession({ARTICLE_URL: broken_html})
    with pytest.raises(UsaTodayTradeValueFetchError):
        fetch_trade_chart(ARTICLE_URL, positions=["WR"], session=session)


def test_fetch_raises_on_request_failure():
    session = FakeSession({}, raise_for={ARTICLE_URL})
    with pytest.raises(UsaTodayTradeValueFetchError):
        fetch_trade_chart(ARTICLE_URL, session=session)