"""Justin Boone's rest-of-season trade value charts, scraped from his Yahoo
Sports article pages -- there's no JSON API for this data, unlike weekly
rankings' `api/fanPro/` endpoint (yahoo_weekly_consensus.py). Confirmed
server-rendered 2026-09-11: a plain `requests.get` with a real user-agent
returns the full <table class="content-table"> already in the HTML, no JS
execution needed.

Article URLs aren't predictable/guessable week to week (random numeric
suffix), so this discovers each week's 4 position URLs by scanning Boone's
author page (sports.yahoo.com/author/justin-boone/, which always lists his
most recent articles) for links matching the trade-value-charts URL shape,
rather than depending on Yahoo's obfuscated, build-churning CSS class names.
"""

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

AUTHOR_URL = "https://sports.yahoo.com/author/justin-boone/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
POSITIONS = ["QB", "RB", "WR", "TE"]

# URL slug format changed for the 2026 season -- confirmed live 2026-09-17:
# .../2026-trade-value-charts--justin-boones-fantasy-football-wide-receiver-
# breakdown-for-week-2-172248093.html (position spelled out, week number
# embedded as its own group) instead of the old .../justin-boones-wr-trade-
# value-charts... shape.
_LINK_RE = re.compile(
    r'href="(/fantasy/article/[^"]*trade-value-charts--justin-boones-fantasy-football-'
    r'(quarterback|running-back|wide-receiver|tight-end)-breakdown-for-week-(\d+)[^"]*)"'
)
_POSITION_SLUG_TO_CODE = {
    "quarterback": "QB",
    "running-back": "RB",
    "wide-receiver": "WR",
    "tight-end": "TE",
}


class BooneTradeValueFetchError(RuntimeError):
    pass


@dataclass
class TradeValueTableRow:
    rank: int | None
    player_name: str
    value_col1_label: str
    value_col1: float | None
    value_col2_label: str
    value_col2: float | None


def discover_position_urls(
    week: int, session: requests.Session | None = None
) -> dict[str, str]:
    """Finds this week's trade-value article URL for each position by
    scanning Boone's author page. A position whose link isn't present for
    `week` is simply absent from the result -- Boone doesn't publish all 4
    on the same day, so this is "not yet available," not an error (mirrors
    how yahoo_weekly_consensus.py treats an unpublished expert)."""
    sess = session or requests.Session()
    try:
        response = sess.get(AUTHOR_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise BooneTradeValueFetchError(f"Failed to fetch {AUTHOR_URL}: {exc}") from exc

    urls: dict[str, str] = {}
    for match in _LINK_RE.finditer(html):
        relative_url, position_slug, url_week = match.group(1), match.group(2), match.group(3)
        if int(url_week) != week:
            continue
        position = _POSITION_SLUG_TO_CODE[position_slug]
        urls[position] = "https://sports.yahoo.com" + relative_url
    return urls


def fetch_position_trade_values(
    position: str, url: str, session: requests.Session | None = None
) -> list[TradeValueTableRow]:
    sess = session or requests.Session()
    try:
        response = sess.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise BooneTradeValueFetchError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="content-table")
    if table is None:
        raise BooneTradeValueFetchError(
            f"No 'content-table' found on {url} -- page layout may have changed."
        )

    trs = table.find_all("tr")
    if len(trs) < 2:
        raise BooneTradeValueFetchError(f"Trade value table on {url} has no data rows.")

    header_cells = [td.get_text(strip=True) for td in trs[0].find_all("td")]
    if len(header_cells) != 4 or header_cells[0] != "Rk" or header_cells[1] != "Player":
        raise BooneTradeValueFetchError(
            f"Unexpected table header on {url}: {header_cells!r} -- expected "
            "['Rk', 'Player', <col1>, <col2>]."
        )
    col1_label, col2_label = header_cells[2], header_cells[3]

    rows: list[TradeValueTableRow] = []
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) != 4:
            continue
        rank_text, player_name, val1_text, val2_text = cells
        rows.append(TradeValueTableRow(
            rank=int(rank_text) if rank_text.isdigit() else None,
            player_name=player_name,
            value_col1_label=col1_label,
            value_col1=_parse_float(val1_text),
            value_col2_label=col2_label,
            value_col2=_parse_float(val2_text),
        ))
    return rows


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def fetch_all_positions(
    week: int,
    positions: list[str] | None = None,
    request_delay: float = 0.5,
    session: requests.Session | None = None,
) -> dict[str, tuple[str, list[TradeValueTableRow]]]:
    """Returns {position: (source_url, rows)} for every requested position
    whose article was found published for `week`. A position missing from
    the result means "not published yet," not a failure -- callers decide
    what to do with a partial result."""
    sess = session or requests.Session()
    wanted = positions or POSITIONS
    urls = discover_position_urls(week, session=sess)
    result: dict[str, tuple[str, list[TradeValueTableRow]]] = {}
    for position in wanted:
        if position not in urls:
            continue
        rows = fetch_position_trade_values(position, urls[position], session=sess)
        result[position] = (urls[position], rows)
        time.sleep(request_delay)
    return result
