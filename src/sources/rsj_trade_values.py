"""Roto Street Journal's (RSJ) fantasy football trade value chart, scraped
directly from its 4 separate position pages -- confirmed live 2026-09-17: a
plain `requests.get` with a real user-agent returns the data table (a
TablePress plugin table, class starting "tablepress") already
server-rendered in the HTML, no JS execution needed. Built from "The Wolf of
Roto Street"'s rest-of-season rankings, explicitly full-PPR/1QB per the
article text -- there's no half-PPR variant published.

Unlike CBS/Boone (one combined article, or one article per position from a
predictable author page), RSJ publishes 4 fully separate URLs per week (one
per position) under unpredictable date-stamped paths
(/YYYY/MM/DD/YYYY-fantasy-football-week-N-trade-value-chart[-position]/),
so this discovers all 4 from RSJ's "trade-value-chart" tag archive
(rotostreetjournal.com/tag/trade-value-chart/, which lists every position's
page for every week) rather than trying to construct URLs directly. Slug
quirk confirmed live: the QB page has NO position suffix at all
(...-trade-value-chart/), and the TE page uses "charts" (plural) where
RB/WR use "chart" (singular) -- e.g. ...-trade-value-charts-tight-ends/ vs
...-trade-value-chart-wide-receivers/. Both are handled explicitly below;
if RSJ ever normalizes this, the regex still matches either spelling.
"""

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

TAG_ARCHIVE_URL = "https://www.rotostreetjournal.com/tag/trade-value-chart/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
POSITIONS = ["QB", "RB", "WR", "TE"]

# Matches all 4 URL shapes: QB has no suffix, RB/WR use "chart-<slug>", TE
# uses "charts-tight-ends" (plural, confirmed live -- an RSJ inconsistency,
# not a bug here).
_LINK_RE = re.compile(
    r'href="(https://www\.rotostreetjournal\.com/\d{4}/\d{2}/\d{2}/'
    r'\d{4}-fantasy-football-week-(\d+)-trade-value-charts?'
    r'(-running-backs|-wide-receivers|-tight-ends)?/)"'
)
_SUFFIX_TO_POSITION = {
    None: "QB",
    "-running-backs": "RB",
    "-wide-receivers": "WR",
    "-tight-ends": "TE",
}


class RsjTradeValueFetchError(RuntimeError):
    pass


@dataclass
class TradeValueTableRow:
    rank: int | None
    player_name: str
    team: str | None
    value_col1_label: str
    value_col1: float | None
    value_col2_label: str
    value_col2: float | None


def discover_position_urls(
    week: int, session: requests.Session | None = None
) -> dict[str, str]:
    """Finds this week's trade-value-chart URL for each position by
    scanning RSJ's tag archive page. A position whose link isn't present
    for `week` is simply absent from the result -- mirrors
    boone_trade_values.py's "not yet available" handling."""
    sess = session or requests.Session()
    try:
        response = sess.get(TAG_ARCHIVE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        raise RsjTradeValueFetchError(f"Failed to fetch {TAG_ARCHIVE_URL}: {exc}") from exc

    urls: dict[str, str] = {}
    for match in _LINK_RE.finditer(html):
        url, url_week, suffix = match.group(1), match.group(2), match.group(3)
        if int(url_week) != week:
            continue
        position = _SUFFIX_TO_POSITION[suffix]
        urls[position] = url
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
        raise RsjTradeValueFetchError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=lambda c: bool(c) and "tablepress" in c)
    if table is None:
        raise RsjTradeValueFetchError(
            f"No 'tablepress' table found on {url} -- page layout may have changed."
        )

    trs = table.find_all("tr")
    if len(trs) < 2:
        raise RsjTradeValueFetchError(f"Trade value table on {url} has no data rows.")

    header_cells = [c.get_text(strip=True).lower() for c in trs[0].find_all(["td", "th"])]
    try:
        rank_idx = header_cells.index("rank")
        name_idx = header_cells.index("player name")
        team_idx = header_cells.index("team")
        value_idx = header_cells.index("value")
    except ValueError as exc:
        raise RsjTradeValueFetchError(
            f"Unexpected table header on {url}: {header_cells!r} -- expected "
            "'rank', 'player name', 'team' and 'value'."
        ) from exc

    rows: list[TradeValueTableRow] = []
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) <= value_idx:
            continue
        rank_text = cells[rank_idx]
        rows.append(TradeValueTableRow(
            rank=int(rank_text) if rank_text.isdigit() else None,
            player_name=cells[name_idx],
            team=cells[team_idx] or None,
            value_col1_label="PPR",
            value_col1=_parse_float(cells[value_idx]),
            value_col2_label="N/A",
            value_col2=None,
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
    whose page was found published for `week`. A position missing from the
    result means "not published yet," not a failure -- callers decide what
    to do with a partial result."""
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
