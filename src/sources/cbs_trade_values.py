"""CBS Sports' (Dave Richard) trade value chart, scraped directly from the
article page -- confirmed live 2026-09-17: a plain `requests.get` with a
real user-agent returns the full 4 position tables (class="TableBuilder",
in QB/RB/WR/TE order) already server-rendered in the HTML, no JS execution
needed.

The weekly article's slug isn't guessable ahead of time (wording varies --
e.g. "...help-you-win-now"), so this discovers the current week's URL by
scanning CBS's fantasy football news hub
(cbssports.com/fantasy/football/news/, which always links the newest
trade-chart article) for a href matching "week-N-trade-chart", rather than
trying to construct the URL directly.

CBS publishes one combined article per week (not 4 separate position
articles like Boone), with each position's table offering 3 value columns:
for RB/WR/TE a non-PPR, half-PPR ("0.5"), and full-PPR ("PPR") value; for QB
a 1QB-4pt-passing-TD, 1QB-6pt-passing-TD, and 2QB value (QB values aren't
PPR-sensitive -- CBS instead varies them by passing-TD point value and
1QB/2QB league size). Per Jared's request for half+full PPR coverage, this
keeps the half-PPR/full-PPR pair for RB/WR/TE and the 1QB-6pt/2QB pair for
QB, dropping the third (non-PPR / 4pt) column entirely, to match
TradeValueRow's two-value-column shape -- see
normalize.cbs_trade_values_to_rows.

Rows aren't numbered in the source table -- they're pre-sorted by value
descending, so rank is derived from row order (1-based) within each
position's table.
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

NEWS_HUB_URL = "https://www.cbssports.com/fantasy/football/news/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
POSITIONS = ["QB", "RB", "WR", "TE"]

_LINK_RE = re.compile(
    r'href="(/fantasy/football/news/[^"]*-week-(\d+)-trade-chart[^"]*)"'
)

# Which two of the source table's three value columns to keep, per position,
# and the label to store them under. Header text is matched lowercased.
_VALUE_COLUMNS = {
    "QB": {"col1": ("1qb-6", "1QB"), "col2": ("2qb", "2QB")},
    "RB": {"col1": ("0.5", "HALF"), "col2": ("ppr", "PPR")},
    "WR": {"col1": ("0.5", "HALF"), "col2": ("ppr", "PPR")},
    "TE": {"col1": ("0.5", "HALF"), "col2": ("ppr", "PPR")},
}


class CbsTradeValueFetchError(RuntimeError):
    pass


@dataclass
class TradeValueTableRow:
    rank: int
    player_name: str
    team: str | None
    value_col1_label: str
    value_col1: float | None
    value_col2_label: str
    value_col2: float | None


def discover_article_url(week: int, session: requests.Session | None = None) -> str | None:
    """Finds this week's trade-chart article URL on CBS's fantasy news hub.
    Returns None if not found (not yet published) rather than raising --
    mirrors boone_trade_values.py's "not yet available" handling."""
    sess = session or requests.Session()
    try:
        response = sess.get(NEWS_HUB_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise CbsTradeValueFetchError(f"Failed to fetch {NEWS_HUB_URL}: {exc}") from exc

    for match in _LINK_RE.finditer(html):
        relative_url, url_week = match.group(1), match.group(2)
        if int(url_week) == week:
            return "https://www.cbssports.com" + relative_url
    return None


def fetch_trade_chart(
    url: str, positions: list[str] | None = None, session: requests.Session | None = None
) -> dict[str, list[TradeValueTableRow]]:
    sess = session or requests.Session()
    try:
        response = sess.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise CbsTradeValueFetchError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="TableBuilder")
    if len(tables) != len(POSITIONS):
        raise CbsTradeValueFetchError(
            f"Expected {len(POSITIONS)} position tables (class=TableBuilder) on "
            f"{url}, found {len(tables)} -- page layout may have changed."
        )

    wanted = positions or POSITIONS
    result: dict[str, list[TradeValueTableRow]] = {}
    for position, table in zip(POSITIONS, tables):
        if position not in wanted:
            continue
        result[position] = _parse_table(position, table, url)
    return result


def _parse_table(position: str, table, url: str) -> list[TradeValueTableRow]:
    trs = table.find_all("tr")
    if len(trs) < 2:
        raise CbsTradeValueFetchError(f"{position} table on {url} has no data rows.")

    header_cells = [c.get_text(strip=True).lower() for c in trs[0].find_all(["td", "th"])]
    col_spec = _VALUE_COLUMNS[position]
    try:
        col1_idx = header_cells.index(col_spec["col1"][0])
        col2_idx = header_cells.index(col_spec["col2"][0])
    except ValueError as exc:
        raise CbsTradeValueFetchError(
            f"Unexpected {position} table header on {url}: {header_cells!r} -- "
            f"expected to find {col_spec['col1'][0]!r} and {col_spec['col2'][0]!r}."
        ) from exc

    rows: list[TradeValueTableRow] = []
    rank = 0
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue
        rank += 1
        rows.append(TradeValueTableRow(
            rank=rank,
            player_name=cells[0],
            team=cells[1] or None,
            value_col1_label=col_spec["col1"][1],
            value_col1=_parse_float(cells[col1_idx]),
            value_col2_label=col_spec["col2"][1],
            value_col2=_parse_float(cells[col2_idx]),
        ))
    return rows


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None
