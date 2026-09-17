"""FantasyPros' trade value chart, scraped directly from the article page --
confirmed live 2026-09-17: a plain `requests.get` with a real user-agent
returns all 4 position tables (plain <table> tags, no class, in QB/RB/WR/TE
order) already server-rendered in the HTML, no JS execution needed.

The weekly article's URL follows a predictable slug
(fantasy-football-trade-value-chart-week-N-YYYY) but is nested under a
publish-date path (/YYYY/MM/...) that isn't knowable in advance, so this
discovers the current week's full URL by scanning FantasyPros' trade-value
chart hub page (fantasypros.com/content/nfl-trade-value-chart/, which lists
every week's article) for a href matching "trade-value-chart-week-N-YYYY",
rather than trying to construct the URL directly.

FantasyPros doesn't label its primary "Value" column with a scoring format
(no half/full-PPR split is stated on the page) -- it's stored as a single
blended value under label "VALUE". QB rows carry an additional "2QB Value"
column and TE rows an additional "TEP Value" (tight-end-premium) column,
stored as the second value column; RB/WR rows have no second column, so
value_col2 is None with label "N/A" -- matches TradeValueRow's
two-value-column shape without inventing a distinction the source doesn't
make. See normalize.fantasypros_trade_values_to_rows.

Rows aren't numbered in the source table -- they're pre-sorted by value
descending, so rank is derived from row order (1-based) within each
position's table.
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HUB_URL = "https://www.fantasypros.com/content/nfl-trade-value-chart/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
POSITIONS = ["QB", "RB", "WR", "TE"]

_LINK_RE = re.compile(
    r'href="(https://www\.fantasypros\.com/\d{4}/\d{2}/fantasy-football-trade-value-chart-'
    r'week-(\d+)-\d{4}/)"'
)

# Position-specific second value column (label, header substring to match).
# None means the position's table has no second value column at all.
_SECOND_VALUE_COLUMN = {
    "QB": ("2QB", "2qb value"),
    "RB": None,
    "WR": None,
    "TE": ("TEP", "tep value"),
}


class FantasyProsTradeValueFetchError(RuntimeError):
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
    """Finds this week's trade-value-chart article URL on FantasyPros' hub
    page. Returns None if not found (not yet published) rather than raising
    -- mirrors boone_trade_values.py's "not yet available" handling."""
    sess = session or requests.Session()
    try:
        response = sess.get(HUB_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise FantasyProsTradeValueFetchError(f"Failed to fetch {HUB_URL}: {exc}") from exc

    for match in _LINK_RE.finditer(html):
        url, url_week = match.group(1), match.group(2)
        if int(url_week) == week:
            return url
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
        raise FantasyProsTradeValueFetchError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) != len(POSITIONS):
        raise FantasyProsTradeValueFetchError(
            f"Expected {len(POSITIONS)} position tables on {url}, found "
            f"{len(tables)} -- page layout may have changed."
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
        raise FantasyProsTradeValueFetchError(f"{position} table on {url} has no data rows.")

    header_cells = [c.get_text(strip=True).lower() for c in trs[0].find_all(["td", "th"])]
    try:
        name_idx = header_cells.index("name")
        team_idx = header_cells.index("team")
        value_idx = header_cells.index("value")
    except ValueError as exc:
        raise FantasyProsTradeValueFetchError(
            f"Unexpected {position} table header on {url}: {header_cells!r} -- "
            "expected to find 'name', 'team' and 'value'."
        ) from exc

    second_col = _SECOND_VALUE_COLUMN[position]
    second_idx = None
    if second_col is not None:
        try:
            second_idx = header_cells.index(second_col[1])
        except ValueError as exc:
            raise FantasyProsTradeValueFetchError(
                f"Unexpected {position} table header on {url}: {header_cells!r} -- "
                f"expected to find {second_col[1]!r}."
            ) from exc

    rows: list[TradeValueTableRow] = []
    rank = 0
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) <= value_idx:
            continue
        rank += 1
        rows.append(TradeValueTableRow(
            rank=rank,
            player_name=cells[name_idx],
            team=cells[team_idx] or None,
            value_col1_label="VALUE",
            value_col1=_parse_float(cells[value_idx]),
            value_col2_label=second_col[0] if second_col else "N/A",
            value_col2=_parse_float(cells[second_idx]) if second_idx is not None else None,
        ))
    return rows


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None
