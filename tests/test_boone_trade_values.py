"""Parser/discovery tests against real captured Yahoo HTML (2026-09-11),
trimmed to a handful of rows -- shape otherwise unmodified. RB uses the
HALF/PPR column pair; QB uses 1QB/2QB -- confirms the parser reads column
labels from the page rather than hardcoding either pair."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import requests

from src.sources.boone_trade_values import (
    BooneTradeValueFetchError,
    discover_position_urls,
    fetch_all_positions,
    fetch_position_trade_values,
)

RB_TABLE_HTML = """
<h2 class="heading" id="jump-link-rest-of-season-rb-trade-values"><strong>Rest-of-season RB trade values</strong></h2><div class="content-table-wrapper"><table class="content-table"><tbody><tr><td colSpan="1" rowSpan="1"><p>Rk</p></td><td colSpan="1" rowSpan="1"><p>Player</p></td><td colSpan="1" rowSpan="1"><p>HALF</p></td><td colSpan="1" rowSpan="1"><p>PPR</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>1</p></td><td colSpan="1" rowSpan="1"><p>Jahmyr Gibbs</p></td><td colSpan="1" rowSpan="1"><p>86</p></td><td colSpan="1" rowSpan="1"><p>89</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>2</p></td><td colSpan="1" rowSpan="1"><p>Bijan Robinson</p></td><td colSpan="1" rowSpan="1"><p>77</p></td><td colSpan="1" rowSpan="1"><p>80</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>10</p></td><td colSpan="1" rowSpan="1"><p>De&#x27;Von Achane</p></td><td colSpan="1" rowSpan="1"><p>58</p></td><td colSpan="1" rowSpan="1"><p>61</p></td></tr></tbody></table>
"""

QB_TABLE_HTML = """
<h2 class="heading" id="jump-link-rest-of-season-qb-trade-values"><strong>Rest-of-season QB trade values</strong></h2><div class="content-table-wrapper"><table class="content-table"><tbody><tr><td colSpan="1" rowSpan="1"><p>Rk</p></td><td colSpan="1" rowSpan="1"><p>Player</p></td><td colSpan="1" rowSpan="1"><p>1QB</p></td><td colSpan="1" rowSpan="1"><p>2QB</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>1</p></td><td colSpan="1" rowSpan="1"><p>Josh Allen</p></td><td colSpan="1" rowSpan="1"><p>32</p></td><td colSpan="1" rowSpan="1"><p>81</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>28</p></td><td colSpan="1" rowSpan="1"><p>Fernando Mendoza</p></td><td colSpan="1" rowSpan="1"><p>0</p></td><td colSpan="1" rowSpan="1"><p>21</p></td></tr></tbody></table>
"""

AUTHOR_PAGE_HTML = """
<a href="/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-tight-end-breakdown-for-week-1-194108969.html" class="_ys_1aqsz4n">TE</a>
<a href="/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-wide-receiver-breakdown-for-week-1-193843688.html" class="_ys_1aqsz4n">WR</a>
<a href="/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-running-back-breakdown-for-week-1-193804763.html" class="_ys_1aqsz4n">RB</a>
<a href="/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-quarterback-breakdown-for-week-1-193721885.html" class="_ys_1aqsz4n">QB</a>
<a href="/fantasy/article/fantasy-football-week-2-justin-boones-qb-rankings-000000000.html" class="_ys_1aqsz4n">old week link, no trade-value-charts match</a>
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


def test_discover_position_urls_matches_current_week_and_ignores_others():
    session = FakeSession({
        "https://sports.yahoo.com/author/justin-boone/": AUTHOR_PAGE_HTML,
    })
    urls = discover_position_urls(week=1, session=session)
    assert urls == {
        "TE": "https://sports.yahoo.com/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-tight-end-breakdown-for-week-1-194108969.html",
        "WR": "https://sports.yahoo.com/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-wide-receiver-breakdown-for-week-1-193843688.html",
        "RB": "https://sports.yahoo.com/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-running-back-breakdown-for-week-1-193804763.html",
        "QB": "https://sports.yahoo.com/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-quarterback-breakdown-for-week-1-193721885.html",
    }


def test_discover_position_urls_returns_empty_for_unpublished_week():
    session = FakeSession({
        "https://sports.yahoo.com/author/justin-boone/": AUTHOR_PAGE_HTML,
    })
    urls = discover_position_urls(week=99, session=session)
    assert urls == {}


def test_discover_raises_on_request_failure():
    session = FakeSession(
        {}, raise_for={"https://sports.yahoo.com/author/justin-boone/"}
    )
    with pytest.raises(BooneTradeValueFetchError):
        discover_position_urls(week=1, session=session)


def test_fetch_rb_trade_values_uses_half_ppr_columns():
    url = "https://sports.yahoo.com/fantasy/article/rb-page.html"
    session = FakeSession({url: RB_TABLE_HTML})
    rows = fetch_position_trade_values("RB", url, session=session)
    assert len(rows) == 3
    gibbs = rows[0]
    assert gibbs.rank == 1
    assert gibbs.player_name == "Jahmyr Gibbs"
    assert gibbs.value_col1_label == "HALF"
    assert gibbs.value_col1 == 86.0
    assert gibbs.value_col2_label == "PPR"
    assert gibbs.value_col2 == 89.0
    # HTML entity in the source ("De&#x27;Von Achane") decodes correctly:
    assert rows[2].player_name == "De'Von Achane"


def test_fetch_qb_trade_values_uses_1qb_2qb_columns():
    url = "https://sports.yahoo.com/fantasy/article/qb-page.html"
    session = FakeSession({url: QB_TABLE_HTML})
    rows = fetch_position_trade_values("QB", url, session=session)
    assert len(rows) == 2
    assert rows[0].value_col1_label == "1QB"
    assert rows[0].value_col2_label == "2QB"
    # a genuine 0 value (Fernando Mendoza's 1QB value) is NOT None:
    assert rows[1].value_col1 == 0.0


def test_fetch_raises_when_table_missing():
    url = "https://sports.yahoo.com/fantasy/article/broken-page.html"
    session = FakeSession({url: "<p>no table here</p>"})
    with pytest.raises(BooneTradeValueFetchError):
        fetch_position_trade_values("RB", url, session=session)


def test_fetch_raises_on_request_failure():
    url = "https://sports.yahoo.com/fantasy/article/rb-page.html"
    session = FakeSession({}, raise_for={url})
    with pytest.raises(BooneTradeValueFetchError):
        fetch_position_trade_values("RB", url, session=session)


def test_fetch_raises_on_wrong_header_shape():
    url = "https://sports.yahoo.com/fantasy/article/wrong-header-page.html"
    # Header shape check requires header_cells[0] == "Rk" and
    # header_cells[1] == "Player" -- use a header where those two are wrong:
    wrong_header_html = """
    <table class="content-table"><tbody>
    <tr><td>Pos</td><td>Name</td><td>Something</td><td>Else</td></tr>
    <tr><td>1</td><td>Josh Allen</td><td>32</td><td>81</td></tr>
    </tbody></table>
    """
    session = FakeSession({url: wrong_header_html})
    with pytest.raises(BooneTradeValueFetchError):
        fetch_position_trade_values("QB", url, session=session)


def test_fetch_raises_when_table_has_no_data_rows():
    url = "https://sports.yahoo.com/fantasy/article/header-only-page.html"
    header_only_html = """
    <table class="content-table"><tbody>
    <tr><td>Rk</td><td>Player</td><td>HALF</td><td>PPR</td></tr>
    </tbody></table>
    """
    session = FakeSession({url: header_only_html})
    with pytest.raises(BooneTradeValueFetchError):
        fetch_position_trade_values("RB", url, session=session)


RB_ONLY_AUTHOR_PAGE_HTML = """
<a href="/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-running-back-breakdown-for-week-1-193804763.html" class="_ys_1aqsz4n">RB</a>
"""


def test_fetch_all_positions_fetches_each_discovered_position_and_skips_missing():
    author_url = "https://sports.yahoo.com/author/justin-boone/"
    rb_url = "https://sports.yahoo.com/fantasy/article/2026-trade-value-charts--justin-boones-fantasy-football-running-back-breakdown-for-week-1-193804763.html"
    session = FakeSession({
        author_url: RB_ONLY_AUTHOR_PAGE_HTML,
        rb_url: RB_TABLE_HTML,
    })
    result = fetch_all_positions(
        week=1, positions=["RB", "QB"], request_delay=0, session=session,
    )
    # The author page fixture only has an RB link for week 1, so QB
    # (present in `positions` but absent from discovery) is skipped rather
    # than erroring:
    assert list(result.keys()) == ["RB"]
    source_url, rows = result["RB"]
    assert source_url == rb_url
    assert len(rows) == 3
    assert rows[0].player_name == "Jahmyr Gibbs"
