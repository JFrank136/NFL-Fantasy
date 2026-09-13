# Boone Trade Values + Scheduled-Pull Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull Justin Boone's weekly rest-of-season trade value charts (QB/RB/WR/TE) into the pipeline alongside the existing weekly rankings, and make `FantasyInSeasonPull`'s email notifications selective (gameday + first-publish) instead of failure-only, plus add a second Sunday-noon run.

**Architecture:** A new, parallel ingestion unit (`src/sources/boone_trade_values.py` → `src/normalize.py` → `src/storage.py` → `src/validate.py` → `scripts/pull_trade_values.py`) mirrors the existing `draftsharks`/`yahoo_weekly_consensus` pipeline's conventions (append-only CSV, immutable raw snapshots, validate-before-write, non-zero exit on failure) but is not folded into `RankingRow`/`pull_week.py`, since trade-value data (rank + two source-labeled value columns) doesn't fit that schema. `scheduled_pull.ps1` gains a trade-values step, a `Send-SuccessEmail` path gated by a small `data/notify_state.json` state file, and (via a one-time manual script) a second Sunday-noon Task Scheduler trigger.

**Tech Stack:** Python 3.11, `requests` + `beautifulsoup4` (both already in `requirements.txt`), `pytest`, PowerShell (`scheduled_pull.ps1`), Windows Task Scheduler.

---

## File Structure

- **Modify** `src/schema.py` — add `TradeValueRow` dataclass + `TRADE_VALUE_COLUMNS`.
- **Create** `src/sources/boone_trade_values.py` — discovers this week's 4 article URLs via Boone's author page, scrapes and parses each position's table.
- **Modify** `src/normalize.py` — add `boone_trade_values_to_rows`.
- **Modify** `src/storage.py` — add `trade_value_raw_snapshot_path` + `append_trade_values_processed`.
- **Modify** `src/validate.py` — add `validate_trade_values`.
- **Create** `scripts/pull_trade_values.py` — the runnable script, mirrors `pull_week.py`'s shape.
- **Create** `tests/test_boone_trade_values.py` — parser/discovery tests against real captured HTML fixtures.
- **Create** `tests/test_validate_trade_values.py` — validation tests (kept separate from `test_validate.py` since it covers a different row type).
- **Modify** `scripts/scheduled_pull.ps1` — run `pull_trade_values.py`, add `Send-SuccessEmail` + notify-state cadence logic.
- **Create** `scripts/add_sunday_noon_trigger.ps1` — one-time, Jared-run script that adds the second Task Scheduler trigger.
- **Modify** `in-season/README.md` — document the new source under "Sources."
- **Modify** `Vampire/INSTRUCTIONS.md` — add the Sunday-trigger one-time step next to the existing failure-email one-time step (same runbook section, same format).

---

### Task 1: `TradeValueRow` schema

**Files:**
- Modify: `src/schema.py`

- [ ] **Step 1: Add the schema**

Add to `src/schema.py`, after the existing `RankingRow` block:

```python
TRADE_VALUE_COLUMNS = [
    "season", "week", "source", "position", "pulled_at", "source_url",
    "rank", "player_name", "team", "value_col1_label", "value_col1",
    "value_col2_label", "value_col2",
]


@dataclass
class TradeValueRow:
    season: int
    week: int              # week this chart was published for
    source: str              # "boone" (room for another expert later)
    position: str
    pulled_at: str            # ISO 8601 timestamp, UTC
    source_url: str
    rank: int | None
    player_name: str
    team: str | None          # not present in the source table -- always None today
    value_col1_label: str      # e.g. "HALF" (RB/WR/TE) or "1QB" (QB)
    value_col1: float | None
    value_col2_label: str      # e.g. "PPR" (RB/WR/TE) or "2QB" (QB)
    value_col2: float | None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in TRADE_VALUE_COLUMNS}


assert [f.name for f in fields(TradeValueRow)] == TRADE_VALUE_COLUMNS, (
    "TradeValueRow fields drifted from TRADE_VALUE_COLUMNS -- keep them in "
    "sync, storage.py's CSV header depends on this exact order"
)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from src.schema import TradeValueRow, TRADE_VALUE_COLUMNS; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
git log -1 --oneline
```
(No git repo exists yet in `in-season/` — skip `git add`/`git commit` for every task in this plan; just verify each step by running the command shown instead. If Jared later initializes git here, these steps become normal commits.)

---

### Task 2: `boone_trade_values.py` source module (TDD)

**Files:**
- Create: `src/sources/boone_trade_values.py`
- Test: `tests/test_boone_trade_values.py`

Real captured fixtures (2026-09-11, trimmed) to use in the test file:

- RB table: `<h2 class="heading" id="jump-link-rest-of-season-rb-trade-values">` header with `HALF`/`PPR` columns.
- QB table: `<h2 class="heading" id="jump-link-rest-of-season-qb-trade-values">` header with `1QB`/`2QB` columns (confirms the module must read column labels from the page, not hardcode `HALF`/`PPR`).
- Author page: real `href="/fantasy/article/...justin-boones-{pos}-trade-value-charts-..."` anchors (confirmed NOT guessable by URL pattern alone — the numeric suffix is unpredictable, so discovery has to scan this page).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_boone_trade_values.py`:

```python
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
    fetch_position_trade_values,
)

RB_TABLE_HTML = """
<h2 class="heading" id="jump-link-rest-of-season-rb-trade-values"><strong>Rest-of-season RB trade values</strong></h2><div class="content-table-wrapper"><table class="content-table"><tbody><tr><td colSpan="1" rowSpan="1"><p>Rk</p></td><td colSpan="1" rowSpan="1"><p>Player</p></td><td colSpan="1" rowSpan="1"><p>HALF</p></td><td colSpan="1" rowSpan="1"><p>PPR</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>1</p></td><td colSpan="1" rowSpan="1"><p>Jahmyr Gibbs</p></td><td colSpan="1" rowSpan="1"><p>86</p></td><td colSpan="1" rowSpan="1"><p>89</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>2</p></td><td colSpan="1" rowSpan="1"><p>Bijan Robinson</p></td><td colSpan="1" rowSpan="1"><p>77</p></td><td colSpan="1" rowSpan="1"><p>80</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>10</p></td><td colSpan="1" rowSpan="1"><p>De&#x27;Von Achane</p></td><td colSpan="1" rowSpan="1"><p>58</p></td><td colSpan="1" rowSpan="1"><p>61</p></td></tr></tbody></table>
"""

QB_TABLE_HTML = """
<h2 class="heading" id="jump-link-rest-of-season-qb-trade-values"><strong>Rest-of-season QB trade values</strong></h2><div class="content-table-wrapper"><table class="content-table"><tbody><tr><td colSpan="1" rowSpan="1"><p>Rk</p></td><td colSpan="1" rowSpan="1"><p>Player</p></td><td colSpan="1" rowSpan="1"><p>1QB</p></td><td colSpan="1" rowSpan="1"><p>2QB</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>1</p></td><td colSpan="1" rowSpan="1"><p>Josh Allen</p></td><td colSpan="1" rowSpan="1"><p>32</p></td><td colSpan="1" rowSpan="1"><p>81</p></td></tr><tr><td colSpan="1" rowSpan="1"><p>28</p></td><td colSpan="1" rowSpan="1"><p>Fernando Mendoza</p></td><td colSpan="1" rowSpan="1"><p>0</p></td><td colSpan="1" rowSpan="1"><p>21</p></td></tr></tbody></table>
"""

AUTHOR_PAGE_HTML = """
<a href="/fantasy/article/fantasy-football-week-1-justin-boones-te-trade-value-charts-194108969.html" class="_ys_1aqsz4n">TE</a>
<a href="/fantasy/article/fantasy-football-week-1-justin-boones-wr-trade-value-charts-193843688.html" class="_ys_1aqsz4n">WR</a>
<a href="/fantasy/article/fantasy-football-week-1-justin-boones-rb-trade-value-charts-193804763.html" class="_ys_1aqsz4n">RB</a>
<a href="/fantasy/article/fantasy-football-week-1-justin-boones-qb-trade-value-charts-193721885.html" class="_ys_1aqsz4n">QB</a>
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
        "TE": "https://sports.yahoo.com/fantasy/article/fantasy-football-week-1-justin-boones-te-trade-value-charts-194108969.html",
        "WR": "https://sports.yahoo.com/fantasy/article/fantasy-football-week-1-justin-boones-wr-trade-value-charts-193843688.html",
        "RB": "https://sports.yahoo.com/fantasy/article/fantasy-football-week-1-justin-boones-rb-trade-value-charts-193804763.html",
        "QB": "https://sports.yahoo.com/fantasy/article/fantasy-football-week-1-justin-boones-qb-trade-value-charts-193721885.html",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season" && python -m pytest tests/test_boone_trade_values.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'src.sources.boone_trade_values'`

- [ ] **Step 3: Write the implementation**

Create `src/sources/boone_trade_values.py`:

```python
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

AUTHOR_URL = "https://sports.yahoo.com/author/justin-boone/"
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
POSITIONS = ["QB", "RB", "WR", "TE"]

_LINK_RE = re.compile(
    r'href="(/fantasy/article/[^"]*justin-boones-(qb|rb|wr|te)-trade-value-charts[^"]*)"'
)


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

    week_marker = f"week-{week}-"
    urls: dict[str, str] = {}
    for match in _LINK_RE.finditer(html):
        relative_url, position_slug = match.group(1), match.group(2).upper()
        if week_marker not in relative_url:
            continue
        urls[position_slug] = "https://sports.yahoo.com" + relative_url
    return urls


def fetch_position_trade_values(
    position: str, url: str, session: requests.Session | None = None
) -> list[TradeValueTableRow]:
    from bs4 import BeautifulSoup

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_boone_trade_values.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Verify against the live site once**

Run:
```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
python -c "
from src.sources.boone_trade_values import fetch_all_positions
result = fetch_all_positions(week=1)
for pos, (url, rows) in result.items():
    print(pos, len(rows), rows[0])
"
```
Expected: prints QB/RB/WR/TE each with dozens of rows and a real top player — confirms the regex/parser work against the live page, not just the fixture.

---

### Task 3: normalize + storage + validate

**Files:**
- Modify: `src/normalize.py`
- Modify: `src/storage.py`
- Modify: `src/validate.py`
- Test: `tests/test_validate_trade_values.py`

- [ ] **Step 1: Add the normalize function**

Add to `src/normalize.py` (add the import alongside the existing ones at the top, then the function at the bottom):

```python
from src.schema import RankingRow, TradeValueRow
from src.sources.boone_trade_values import TradeValueTableRow
```

```python
def boone_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[TradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="boone", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, team=None,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]
```

- [ ] **Step 2: Add storage functions**

Add to `src/storage.py` (add `TRADE_VALUE_COLUMNS, TradeValueRow` to the existing `from src.schema import ...` line, then add at the bottom):

```python
def trade_value_raw_snapshot_path(
    raw_dir: Path, source: str, season: int, week: int, position: str, pulled_at: str
) -> Path:
    safe_ts = pulled_at.replace(":", "").replace("-", "")
    return raw_dir / source / str(season) / f"week{week:02d}_{position}_{safe_ts}.json"


def append_trade_values_processed(processed_path: Path, rows: list[TradeValueRow]) -> None:
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not processed_path.exists()
    with processed_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_VALUE_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
```

- [ ] **Step 3: Write the failing validate test**

Create `tests/test_validate_trade_values.py`:

```python
from src.schema import TradeValueRow
from src.validate import validate_trade_values


def make_row(player_name="Player", rank=1, **kw):
    defaults = dict(
        season=2026, week=1, source="boone", position="RB",
        pulled_at="2026-09-11T00:00:00+00:00",
        source_url="https://sports.yahoo.com/fantasy/article/x.html",
        rank=rank, player_name=player_name, team=None,
        value_col1_label="HALF", value_col1=50.0,
        value_col2_label="PPR", value_col2=55.0,
    )
    defaults.update(kw)
    return TradeValueRow(**defaults)


def test_empty_pull_is_an_error():
    issues = validate_trade_values([], position="RB")
    assert any(i.severity == "error" for i in issues)


def test_blank_player_name_is_an_error():
    rows = [make_row(player_name="")]
    issues = validate_trade_values(rows, position="RB")
    assert any(i.severity == "error" for i in issues)


def test_below_floor_is_a_warning_not_an_error():
    rows = [make_row(player_name=f"Player {i}") for i in range(3)]
    issues = validate_trade_values(rows, position="RB", floor=30)
    assert any(i.severity == "warning" for i in issues)
    assert not any(i.severity == "error" for i in issues)


def test_healthy_pull_has_no_issues():
    rows = [make_row(player_name=f"Player {i}", rank=i) for i in range(35)]
    issues = validate_trade_values(rows, position="RB", floor=30)
    assert issues == []
```

- [ ] **Step 4: Run to verify it fails**

Run: `python -m pytest tests/test_validate_trade_values.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_trade_values'`

- [ ] **Step 5: Add the validation function**

Add to `src/validate.py` (add `TradeValueRow` to the existing `from src.schema import RankingRow` line, making it `from src.schema import RankingRow, TradeValueRow`), then add at the bottom:

```python
MINIMUM_TRADE_VALUE_COUNTS = {"QB": 15, "RB": 30, "WR": 30, "TE": 8}


def validate_trade_values(
    rows: list[TradeValueRow], position: str, floor: int | None = None
) -> list[ValidationIssue]:
    if not rows:
        return [ValidationIssue(
            "error", f"Trade value pull for {position} returned zero rows."
        )]
    issues: list[ValidationIssue] = []
    missing_name = sum(1 for r in rows if not r.player_name)
    if missing_name:
        issues.append(ValidationIssue(
            "error",
            f"{missing_name}/{len(rows)} {position} trade-value rows have a "
            "blank player_name.",
        ))
    effective_floor = floor if floor is not None else MINIMUM_TRADE_VALUE_COUNTS.get(position, 5)
    if len(rows) < effective_floor:
        issues.append(ValidationIssue(
            "warning",
            f"Only {len(rows)} {position} trade-value rows (expected at "
            f"least {effective_floor}) -- may be a partial pull.",
        ))
    return issues
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_validate_trade_values.py tests/test_boone_trade_values.py -v`
Expected: PASS (12 tests total)

---

### Task 4: `scripts/pull_trade_values.py`

**Files:**
- Create: `scripts/pull_trade_values.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python
"""Pulls Justin Boone's rest-of-season trade value charts (QB/RB/WR/TE) for
the current week and writes them to data/raw/boone_trade_values/ (immutable
snapshot) and data/processed/trade_values_long.csv (append).

Usage:
    python scripts/pull_trade_values.py               # current week, all 4 positions
    python scripts/pull_trade_values.py --week 2       # force a specific week
    python scripts/pull_trade_values.py --position rb,wr

A position not yet published for the target week is skipped (not an error --
see src/sources/boone_trade_values.py). Exits non-zero only on a validation
error or unexpected failure. Writes data/last_trade_values_status.json
(position -> ok|failed: <reason>|not_yet_published) so an external check
(scheduled_pull.ps1) can tell success from failure without parsing console
text.
"""

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import normalize, season_config, storage, validate
from src.sources.boone_trade_values import (
    POSITIONS,
    BooneTradeValueFetchError,
    discover_position_urls,
    fetch_position_trade_values,
)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "trade_values_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_trade_values_status.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, default=None, help="Defaults to the current active week.")
    parser.add_argument("--season", type=int, default=season_config.SEASON)
    parser.add_argument("--position", default="all", help="Comma list (qb,rb,wr,te), or 'all'")
    args = parser.parse_args()

    week = args.week if args.week is not None else season_config.current_week()
    wanted_positions = (
        POSITIONS if args.position == "all"
        else [p.strip().upper() for p in args.position.split(",")]
    )

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(f"Starting Boone trade-value pull -- week {week}, positions {wanted_positions}")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    try:
        urls = discover_position_urls(week)
    except BooneTradeValueFetchError as e:
        print(f"\n[FAILED] Could not discover this week's article URLs: {e}")
        _write_status({p: f"failed: could not discover URLs: {e}" for p in wanted_positions})
        sys.exit(1)

    run_status = {}
    any_errors = False
    success_count = 0

    for i, position in enumerate(wanted_positions, 1):
        print(f"[{i}/{len(wanted_positions)}] {position}...")
        if position not in urls:
            print("   Not yet published for this week -- skipping.")
            run_status[position] = "not_yet_published"
            continue

        url = urls[position]
        try:
            table_rows = fetch_position_trade_values(position, url)
        except BooneTradeValueFetchError as e:
            print(f"\n[FAILED] {position}: {e}")
            any_errors = True
            run_status[position] = f"failed: {e}"
            continue
        except Exception as e:
            print(f"\n[FAILED] Unexpected failure on {position}: {e}")
            traceback.print_exc()
            run_status[position] = f"failed: unexpected error: {e}"
            _write_status(run_status, any_errors=True)
            sys.exit(1)

        issues = validate.validate_trade_values(table_rows, position=position)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"   [{tag}] {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[position] = "failed: " + "; ".join(
                i.message for i in issues if i.severity == "error"
            )
            print(f"   Not writing output for {position} -- validation failed.")
            continue

        rows = normalize.boone_trade_values_to_rows(
            position, url, table_rows, args.season, week, pulled_at
        )
        snapshot_path = storage.trade_value_raw_snapshot_path(
            RAW_DIR / "boone_trade_values", "boone", args.season, week, position, pulled_at
        )
        storage.write_raw_snapshot(snapshot_path, table_rows)
        storage.append_trade_values_processed(PROCESSED_PATH, rows)
        run_status[position] = "ok"
        success_count += 1
        print(f"   {len(rows)} rows -> {snapshot_path.relative_to(BASE_DIR)}")

    elapsed = datetime.now() - start
    mins, secs = elapsed.seconds // 60, elapsed.seconds % 60
    print(f"\n{'=' * 45}")
    print(f"Done: {success_count}/{len(wanted_positions)} position(s) written")
    print(f"Time: {mins}m {secs}s")
    print(f"Processed output: {PROCESSED_PATH.resolve()}")
    print(f"{'=' * 45}")

    _write_status(run_status, any_errors=any_errors)
    if any_errors:
        sys.exit(1)


def _write_status(run_status: dict, any_errors: bool = True) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ok": not any_errors,
                "positions": run_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
```

Note: `storage.write_raw_snapshot` (existing function) takes `list` and calls
`asdict(r)` on each element — `TradeValueTableRow` is a dataclass too, so this
works unchanged; no new raw-snapshot writer needed.

- [ ] **Step 2: Run it against the live site**

Run:
```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
python scripts/pull_trade_values.py
```
Expected: exit code 0, a `Done: 4/4 position(s) written` summary, and new
files under `data/raw/boone_trade_values/2026/` and
`data/processed/trade_values_long.csv`.

- [ ] **Step 3: Spot-check the CSV**

Run: `python -c "import csv; rows = list(csv.DictReader(open('data/processed/trade_values_long.csv', encoding='utf-8'))); print(len(rows)); print(rows[0]); print(rows[-1])"`
Expected: a few hundred rows total (QB+RB+WR+TE), first/last rows show
plausible player names and numeric `value_col1`/`value_col2`.

---

### Task 5: Wire into `scheduled_pull.ps1` + notify-state success email

**Files:**
- Modify: `scripts/scheduled_pull.ps1`

- [ ] **Step 1: Read the current file to confirm line numbers before editing**

Run: `Get-Content "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season\scripts\scheduled_pull.ps1" | Measure-Object -Line`
(Confirms the file hasn't drifted from the version this plan was written
against — 131 lines as of 2026-09-11. If different, re-read the file before
editing rather than assuming these edits still apply cleanly.)

- [ ] **Step 2: Add the trade-values pull step and a combined exit-status check**

In `scheduled_pull.ps1`, immediately after the existing block that runs
`pull_week.py` and computes `$pullExit` (originally lines 66-69):

```powershell
    Log "Running pull_week.py..."
    & $PythonExe "scripts\pull_week.py" 2>&1 | ForEach-Object { Log $_ }
    $pullExit = $LASTEXITCODE
    Log "pull_week.py exit code: $pullExit"
```

add directly below it:

```powershell
    Log "Running pull_trade_values.py..."
    & $PythonExe "scripts\pull_trade_values.py" 2>&1 | ForEach-Object { Log $_ }
    $tradeValuesExit = $LASTEXITCODE
    Log "pull_trade_values.py exit code: $tradeValuesExit"
```

- [ ] **Step 3: Fold the trade-values exit code into the failure check**

Find the existing block near the end (originally lines 116-121):

```powershell
    if ($pullExit -ne 0) {
        Log "=== FINISHED WITH FAILURES -- see above / last_run_status.json ==="
        Send-FailureEmail "Fantasy pull FAILED ($(Get-Date -Format 'yyyy-MM-dd'))" "pull_week.py exited with code $pullExit.`n`nFull log: $LogFile`n`nTail of log:`n$(Get-Content $LogFile -Tail 40 | Out-String)"
    } else {
        Log "=== FINISHED OK ==="
    }
```

Replace it with:

```powershell
    $anyFailure = ($pullExit -ne 0) -or ($tradeValuesExit -ne 0)
    if ($anyFailure) {
        Log "=== FINISHED WITH FAILURES -- see above / status JSON files ==="
        $failedParts = @()
        if ($pullExit -ne 0) { $failedParts += "pull_week.py exited $pullExit" }
        if ($tradeValuesExit -ne 0) { $failedParts += "pull_trade_values.py exited $tradeValuesExit" }
        Send-FailureEmail "Fantasy pull FAILED ($(Get-Date -Format 'yyyy-MM-dd'))" "$($failedParts -join '; ').`n`nFull log: $LogFile`n`nTail of log:`n$(Get-Content $LogFile -Tail 40 | Out-String)"
    } else {
        Log "=== FINISHED OK ==="
        Send-SuccessEmailIfWarranted -CurrentWeek $currentWeek -CsvPath $csvPath
    }
```

- [ ] **Step 4: Change the final exit code to reflect both pulls**

Find (originally line 130):

```powershell
exit $pullExit
```

Replace with:

```powershell
if ($pullExit -ne 0) { exit $pullExit }
exit $tradeValuesExit
```

- [ ] **Step 5: Add the notify-state helpers and `Send-SuccessEmail`**

Add these functions right after the existing `Send-FailureEmail` function
definition (originally lines 26-39), before the `Log "=== Scheduled pull starting ==="` line:

```powershell
$NotifyStatePath = Join-Path $InSeasonDir "data\notify_state.json"

function Get-NotifyState {
    # Windows PowerShell 5.1's ConvertFrom-Json has no -AsHashtable (that's
    # PS 6+/Core only) -- convert the returned PSCustomObject by hand.
    if (Test-Path $NotifyStatePath) {
        $obj = Get-Content $NotifyStatePath -Raw | ConvertFrom-Json
        $hash = @{}
        foreach ($prop in $obj.PSObject.Properties) {
            $hash[$prop.Name] = $prop.Value
        }
        return $hash
    }
    return @{}
}

function Save-NotifyState($state) {
    $state | ConvertTo-Json | Set-Content -Path $NotifyStatePath -Encoding utf8
}

function Send-SuccessEmail($subject, $body) {
    if (-not (Test-Path $CredPath)) {
        Log "No stored Gmail credential at $CredPath -- skipping success email."
        return
    }
    try {
        $cred = Import-Clixml -Path $CredPath
        Send-MailMessage -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred `
            -From $cred.UserName -To $cred.UserName -Subject $subject -Body $body
        Log "Success email sent to $($cred.UserName)."
    } catch {
        Log "Failed to send success email: $_"
    }
}

function Send-SuccessEmailIfWarranted($CurrentWeek, $CsvPath) {
    $state = Get-NotifyState
    $today = Get-Date
    $isGameday = $today.DayOfWeek -in @("Thursday", "Sunday", "Monday")

    $rankingsStatusPath = Join-Path $InSeasonDir "data\last_run_status.json"
    $tradeValuesStatusPath = Join-Path $InSeasonDir "data\last_trade_values_status.json"
    $newlyPublished = @()

    if (Test-Path $rankingsStatusPath) {
        $rankingsStatus = Get-Content $rankingsStatusPath -Raw | ConvertFrom-Json
        foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
            if ($combo.Value -eq "ok") {
                $key = "rankings:$($combo.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += $combo.Name
                    $state[$key] = "sent"
                }
            }
        }
    }
    if (Test-Path $tradeValuesStatusPath) {
        $tvStatus = Get-Content $tradeValuesStatusPath -Raw | ConvertFrom-Json
        foreach ($pos in $tvStatus.positions.PSObject.Properties) {
            if ($pos.Value -eq "ok") {
                $key = "tradevalue:week$CurrentWeek:$($pos.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += "trade-values/$($pos.Name)"
                    $state[$key] = "sent"
                }
            }
        }
    }

    Save-NotifyState $state

    if (-not $isGameday -and $newlyPublished.Count -eq 0) {
        Log "Success email skipped -- not a gameday and nothing newly published."
        return
    }

    $reason = if ($isGameday -and $newlyPublished.Count -gt 0) {
        "gameday + first publish of: $($newlyPublished -join ', ')"
    } elseif ($isGameday) {
        "gameday"
    } else {
        "first publish of: $($newlyPublished -join ', ')"
    }
    Log "Sending success email ($reason)."
    Send-SuccessEmail "Fantasy pull OK ($(Get-Date -Format 'yyyy-MM-dd')) -- $reason" `
        "Week $CurrentWeek pull succeeded.`n`nReason for this email: $reason`n`nLog: $LogFile"
}
```

- [ ] **Step 6: Dry-run the script end to end**

Run:
```powershell
powershell -File "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season\scripts\scheduled_pull.ps1"
```
Expected: completes, logs `=== FINISHED OK ===`, and (since today is whatever
day it is when this runs) either sends a success email or logs "skipped --
not a gameday and nothing newly published" — both are correct outcomes,
check the log line matches today's actual gameday/publish state. Confirm
`data\notify_state.json` was created/updated afterward.

- [ ] **Step 7: Confirm re-running doesn't re-send a first-publish email**

Run the same command a second time immediately.
Expected: log shows the same combos already in `notify_state.json`, so
`$newlyPublished` is empty on the second run — email sent only if today is a
gameday, not because of "first publish" a second time.

---

### Task 6: One-time Sunday-noon trigger + docs

**Files:**
- Create: `scripts/add_sunday_noon_trigger.ps1`
- Modify: `in-season/README.md`
- Modify: `Vampire/INSTRUCTIONS.md`

This is a one-time change to live Task Scheduler state on Jared's machine —
written as a script for Jared to run himself (matching how the original
failure-email credential setup was handled), not executed automatically as
part of this plan.

- [ ] **Step 1: Write the setup script**

Create `scripts/add_sunday_noon_trigger.ps1`:

```powershell
# add_sunday_noon_trigger.ps1
#
# One-time setup: adds a second trigger to the existing FantasyInSeasonPull
# task -- Sundays at 12:00pm, alongside the existing daily 6:15am trigger --
# so Sunday's midday ranking adjustments (inactives, weather, late news)
# get picked up same-day instead of waiting until Monday 6:15am. Run this
# once, yourself, in an elevated PowerShell prompt (Task Scheduler changes
# need admin rights the same way the original task did).

$TaskName = "FantasyInSeasonPull"
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop

$existingTriggers = $existingTask.Triggers
$sundayNoonTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "12:00pm"

# Carry over the same wake/network settings the daily trigger already has,
# so the noon run gets the same wake-from-sleep protection.
$sundayNoonTrigger.WakeToRun = $true

$newTriggers = $existingTriggers + $sundayNoonTrigger
Set-ScheduledTask -TaskName $TaskName -Trigger $newTriggers

Write-Output "Done. $TaskName now has $($newTriggers.Count) trigger(s):"
(Get-ScheduledTask -TaskName $TaskName).Triggers | ForEach-Object {
    Write-Output "  $($_.CimClass.CimClassName): $($_.StartBoundary) (DaysOfWeek: $($_.DaysOfWeek))"
}
```

- [ ] **Step 2: Document it in the runbook (Vampire/INSTRUCTIONS.md)**

In `Vampire/INSTRUCTIONS.md`, in the same "Weekly rankings data refresh"
section as the existing "One-time setup: failure email alerts" block, add a
new header + block right after it:

```markdown
#### One-time setup: Sunday noon re-pull

Rankings often get adjusted around midday on Sundays (inactives, weather,
late news) — this adds a second trigger to the existing task so that gets
picked up same-day instead of waiting for the next 6:15am run. Run this
yourself in an **elevated** PowerShell prompt (Task Scheduler changes need
admin rights):
```powershell
powershell -File "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season\scripts\add_sunday_noon_trigger.ps1"
```
```

- [ ] **Step 3: Document the new data source in `in-season/README.md`**

In `in-season/README.md`, under the existing `## Sources` section, add a new
bullet after the "Joel Smyth" one:

```markdown
- **Justin Boone rest-of-season trade values** — scraped directly from
  Boone's Yahoo article pages (`fantasy-football-week-N-justin-boones-{pos}-trade-value-charts`)
  since there's no JSON API for this data. Article URLs aren't
  predictable/guessable week to week, so `src/sources/boone_trade_values.py`
  discovers each week's 4 position URLs from Boone's author page
  (`sports.yahoo.com/author/justin-boone/`) before scraping them. Stored
  separately from weekly rankings — `data/processed/trade_values_long.csv`,
  its own schema (`TradeValueRow`) — since the data shape (rank + two
  source-labeled value columns, e.g. HALF/PPR for RB/WR/TE but 1QB/2QB for
  QB) doesn't fit `RankingRow`.
```

Also update the `## Usage` section's example command block to mention the
new script:

```markdown
python scripts/pull_trade_values.py --week 1
```

- [ ] **Step 4: Verify the docs render sensibly**

Run: `Get-Content "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season\README.md" | Select-String "trade value" -Context 2`
Expected: the new bullet appears, correctly formatted, no stray markdown.

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** Task 1-4 cover "Part 1: Boone trade value ingestion" end
  to end (schema, source module, normalize/storage/validate, script). Task 5
  covers "Part 2: Scheduled-pull notifications" (wiring + success-email
  cadence). Task 6 covers the Sunday-noon trigger and doc updates. Every
  numbered section of the design spec has a corresponding task.
- **No git commits in Tasks 1-4/6**: `in-season/` has no `.git` — every task
  that would normally end in `git add && git commit` instead ends in a
  verification command. If Jared initializes git here later, insert normal
  commit steps after each task.
- **Type consistency check:** `TradeValueRow` field names
  (`value_col1_label`, `value_col1`, `value_col2_label`, `value_col2`) are
  used identically in `schema.py` (Task 1), `normalize.py` (Task 3),
  `boone_trade_values.py`'s `TradeValueTableRow` (Task 2, same field names by
  design so `normalize.py`'s mapping is a straight pass-through), and the
  test fixtures (Task 2/3) — confirmed no drift.
