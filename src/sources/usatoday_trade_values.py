"""USA Today's weekly fantasy-football trade value chart.

USA Today publishes one combined article per week containing separate QB, RB,
WR, and TE trade-value tables. The current article URL is discovered from the
Fantasy Football hub rather than guessed from its date-stamped story path.

The source uses inconsistent value-column names by position:

* QB: ``1QB`` / ``6/TD`` / ``SFLEX`` -- the 1QB value is scoring-format
  agnostic for this pipeline, so it is stored in both HALF and FULL.
* RB: ``STD`` / ``Half`` / ``PPR`` -- keep Half and PPR.
* WR/TE: ``STD`` / ``Half`` / ``Full`` -- keep Half and Full.

The resulting ``TradeValueTableRow`` shape intentionally matches the existing
USA Today normalizer so this module is a drop-in replacement for the previous
external-CSV loader.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HUB_URL = "https://www.usatoday.com/sports/fantasy/football/"
POSITIONS = ["QB", "RB", "WR", "TE"]

# This is the same ordinary browser request shape verified against the live
# hub/article on 2026-09-17. No cookies, tokens, browser automation, or hidden
# endpoints are required.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) "
        "Gecko/20100101 Firefox/156.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_ARTICLE_RE = re.compile(r"fantasy-football-trade-value-chart-week-(\d+)-", re.I)

_POSITION_HEADING = {
    "QB": "quarterback trade value chart",
    "RB": "running back trade value chart",
    "WR": "wide receiver trade value chart",
    "TE": "tight end trade value chart",
}

# Source header -> the two values stored by this pipeline.
_VALUE_COLUMNS = {
    "QB": ("1QB", "1QB"),
    "RB": ("Half", "PPR"),
    "WR": ("Half", "Full"),
    "TE": ("Half", "Full"),
}


class UsaTodayTradeValueFetchError(RuntimeError):
    pass


@dataclass
class TradeValueTableRow:
    rank: int | None
    player_name: str
    value_col1_label: str
    value_col1: float | None
    value_col2_label: str
    value_col2: float | None


def discover_article_url(
    week: int,
    season: int | None = None,
    session: requests.Session | None = None,
) -> str | None:
    """Find this week's USA Today trade-value article from the fantasy hub.

    Returns ``None`` when the requested week is not present yet. When ``season``
    is supplied, links from other seasons are ignored as an extra guard against
    accidentally selecting an older same-week article.
    """
    sess = session or requests.Session()
    try:
        response = sess.get(HUB_URL, headers=REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise UsaTodayTradeValueFetchError(f"Failed to fetch {HUB_URL}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        match = _ARTICLE_RE.search(href)
        if match is None or int(match.group(1)) != week:
            continue

        url = urljoin(HUB_URL, href)
        parsed = urlparse(url)

        # Only accept USA Today story links from the fantasy-football section.
        if not parsed.hostname or not parsed.hostname.endswith("usatoday.com"):
            continue
        if "/story/sports/fantasy/football/" not in parsed.path:
            continue
        if season is not None and f"/{season}/" not in parsed.path:
            continue

        return url

    return None


def fetch_trade_chart(
    url: str,
    positions: list[str] | None = None,
    session: requests.Session | None = None,
) -> dict[str, list[TradeValueTableRow]]:
    """Fetch and parse the requested position tables from one USA Today article."""
    sess = session or requests.Session()
    try:
        response = sess.get(url, headers=REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise UsaTodayTradeValueFetchError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    wanted = positions or POSITIONS

    unknown = [p for p in wanted if p not in POSITIONS]
    if unknown:
        raise UsaTodayTradeValueFetchError(
            f"Unexpected position(s) requested: {unknown!r}; expected only {POSITIONS}."
        )

    result: dict[str, list[TradeValueTableRow]] = {}
    headings = soup.find_all("h2")

    for position in wanted:
        expected_heading = _POSITION_HEADING[position]
        heading = next(
            (
                h
                for h in headings
                if expected_heading in h.get_text(" ", strip=True).lower()
            ),
            None,
        )
        if heading is None:
            raise UsaTodayTradeValueFetchError(
                f"Could not find {position} heading {expected_heading!r} on {url} -- "
                "page layout may have changed or the article is incomplete."
            )

        table = heading.find_next("table")
        if table is None:
            raise UsaTodayTradeValueFetchError(
                f"Could not find a table after the {position} heading on {url}."
            )

        result[position] = _parse_table(position, table, url)

    return result


def _parse_table(position: str, table, url: str) -> list[TradeValueTableRow]:
    header_row = table.find("tr")
    if header_row is None:
        raise UsaTodayTradeValueFetchError(f"{position} table on {url} has no header row.")

    headers = [
        cell.get_text(" ", strip=True)
        for cell in header_row.find_all(["th", "td"])
    ]
    normalized = [header.casefold() for header in headers]

    col1_name, col2_name = _VALUE_COLUMNS[position]
    required = ["RK", "Player", col1_name]
    if col2_name != col1_name:
        required.append(col2_name)

    try:
        rank_idx = normalized.index("rk")
        player_idx = normalized.index("player")
        col1_idx = normalized.index(col1_name.casefold())
        col2_idx = normalized.index(col2_name.casefold())
    except ValueError as exc:
        raise UsaTodayTradeValueFetchError(
            f"Unexpected {position} table header on {url}: {headers!r} -- "
            f"expected to find {required!r}."
        ) from exc

    tbody = table.find("tbody")
    data_rows = tbody.find_all("tr") if tbody is not None else table.find_all("tr")[1:]
    if not data_rows:
        raise UsaTodayTradeValueFetchError(f"{position} table on {url} has no data rows.")

    max_needed_idx = max(rank_idx, player_idx, col1_idx, col2_idx)
    rows: list[TradeValueTableRow] = []

    for row_number, tr in enumerate(data_rows, start=1):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        if len(cells) <= max_needed_idx:
            raise UsaTodayTradeValueFetchError(
                f"Malformed {position} row {row_number} on {url}: {cells!r}; "
                f"header is {headers!r}."
            )

        player_name = cells[player_idx].strip()
        if not player_name:
            raise UsaTodayTradeValueFetchError(
                f"Blank player name in {position} row {row_number} on {url}."
            )

        rank = _parse_int_required(cells[rank_idx], position, "RK", row_number, url)
        value1 = _parse_float_required(cells[col1_idx], position, col1_name, row_number, url)
        value2 = _parse_float_required(cells[col2_idx], position, col2_name, row_number, url)

        rows.append(
            TradeValueTableRow(
                rank=rank,
                player_name=player_name,
                # Preserve the labels produced by the retired external-CSV path
                # so downstream behavior stays unchanged.
                value_col1_label="HALF",
                value_col1=value1,
                value_col2_label="FULL",
                value_col2=value2,
            )
        )

    if not rows:
        raise UsaTodayTradeValueFetchError(f"{position} table on {url} has no player rows.")

    return rows


def _parse_int_required(
    text: str, position: str, column: str, row_number: int, url: str
) -> int:
    try:
        return int(float(text))
    except (TypeError, ValueError) as exc:
        raise UsaTodayTradeValueFetchError(
            f"Invalid {position} {column} value {text!r} in row {row_number} on {url}."
        ) from exc


def _parse_float_required(
    text: str, position: str, column: str, row_number: int, url: str
) -> float:
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise UsaTodayTradeValueFetchError(
            f"Invalid {position} {column} value {text!r} in row {row_number} on {url}."
        ) from exc