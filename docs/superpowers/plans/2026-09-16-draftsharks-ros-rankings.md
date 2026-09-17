# Draft Sharks ROS Rankings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull Draft Sharks' rest-of-season (ROS) rankings (`ros-rankings/load-rows`) into the pipeline, following the exact conventions the weekly-rankings and Boone-trade-values pipelines already use, landing clean validated data in a new `in_season_ros_rankings` Supabase table.

**Architecture:** A new parallel pipeline unit, structurally identical to the Boone trade-values pipeline: new source module (`src/sources/draftsharks_ros.py`) → new row schema (`RosRankingRow`) → new normalize/validate/storage functions → new script (`scripts/pull_draftsharks_ros.py`) → extended `push_to_supabase.py` → extended `scheduled_pull.ps1` (new step, folded into the existing status email via the project's existing dynamic-source-discovery logic, not a new email).

**Tech Stack:** Python 3.11, `requests` + `beautifulsoup4` for scraping, `pytest` for tests, PowerShell 5.1 for the scheduled-task wiring, Supabase (Postgres) via `scripts/push_to_supabase.py`'s REST calls.

**Reference:** `docs/superpowers/specs/2026-09-16-draftsharks-ros-rankings-design.md` — read this first if anything below is ambiguous; this plan implements it task-by-task and shouldn't need to re-justify decisions already made there.

---

## Task 1: `RosRankingRow` schema

**Files:**
- Modify: `src/schema.py`

- [ ] **Step 1: Add the new columns list and dataclass**

Append this to the end of `src/schema.py` (after the existing `TradeValueRow` block):

```python
ROS_RANKING_COLUMNS = [
    "season", "source", "scoring", "pulled_at", "as_of_week",
    "source_player_id", "player_name", "canonical_name", "team", "position",
    "rank", "tier_overall", "tier_positional",
    "projection", "floor_proj", "ceiling_proj",
    "ds_value", "strength_of_schedule", "games_played", "injury_risk", "bye",
]


@dataclass
class RosRankingRow:
    season: int
    source: str            # "draftsharks" (room for another ROS source later)
    scoring: str            # "half-ppr" | "ppr"
    pulled_at: str            # ISO 8601 timestamp, UTC
    as_of_week: int           # season_config.current_week() at pull time --
                              # a snapshot marker, NOT a uniqueness key: ROS
                              # rankings aren't published per-week the way
                              # weekly rankings are.
    source_player_id: str
    player_name: str
    canonical_name: str
    team: str | None
    position: str
    rank: int | None
    tier_overall: int | None
    tier_positional: int | None
    projection: float | None
    floor_proj: float | None
    ceiling_proj: float | None
    ds_value: float | None
    strength_of_schedule: str | None
    games_played: int | None
    injury_risk: str | None
    bye: int | None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in ROS_RANKING_COLUMNS}


assert [f.name for f in fields(RosRankingRow)] == ROS_RANKING_COLUMNS, (
    "RosRankingRow fields drifted from ROS_RANKING_COLUMNS -- keep them in "
    "sync, storage.py's CSV header depends on this exact order"
)
```

- [ ] **Step 2: Verify it imports and the field-order assertion passes**

Run:
```bash
python -c "from src.schema import RosRankingRow, ROS_RANKING_COLUMNS; print('ok')"
```
Expected: `ok` (an `AssertionError` here means the dataclass field order doesn't match `ROS_RANKING_COLUMNS` exactly — fix the order, not the assertion).

- [ ] **Step 3: Commit**

```bash
git add src/schema.py
git commit -m "Add RosRankingRow schema for Draft Sharks ROS rankings"
```

---

## Task 2: Draft Sharks ROS source module

**Files:**
- Create: `src/sources/draftsharks_ros.py`
- Create: `tests/test_draftsharks_ros.py`

- [ ] **Step 1: Write the failing parse test**

Create `tests/test_draftsharks_ros.py`:

```python
"""Parsing test against a constructed fragment shaped like
draftsharks.com/ros-rankings/load-rows -- same tbody[data-player-row]
structure weekly-rankings/load-rows uses, with ROS-specific data-attribute
names (rosWeeklyPts/rosWeeklyFloorPts/rosWeeklyCeilingPts/dsValue/
games_played/player.sipPlayerProfile.injury_prob) substituted in. Not a
live-captured fragment (no live sample was available while writing this) --
verify parsing against a real captured page the first time this runs
against the live endpoint, and update this fixture if field names differ."""

from src.sources.draftsharks_ros import _parse_page, fetch_draftsharks_ros

REAL_FRAGMENT = """
<tbody
    data-player-row
    data-key="13542"
    data-tier-overall="1"
    data-tier-positional="1"
    data-fantasy-position="RB"
    data-player-name="Jahmyr Gibbs"
    data-team-id="11"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>1</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DET.svg" alt="DET logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="-3.9%" data-attribute="strength_of_schedule"><span class="column-title">-3.9%</span></td>
        <td class="ds-cell bye centered" data-value="6" data-attribute="player.team.bye"><span class="column-title">6</span></td>
        <td class="ds-cell games-played centered" data-value="12" data-attribute="games_played"><span class="column-title">12</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="180.5" data-attribute="rosWeeklyFloorPts"><span class="column-title">180.5</span></td>
        <td class="ds-cell ros-proj centered" data-value="220.4" data-attribute="rosWeeklyPts"><span class="column-title">220.4</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="260.1" data-attribute="rosWeeklyCeilingPts"><span class="column-title">260.1</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="95.0" data-attribute="dsValue"><span class="column-title">95.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="8" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">8</span></td>
    </tr>
</tbody>

<tbody
    data-player-row
    data-key="34984"
    data-tier-overall="7"
    data-tier-positional="2"
    data-fantasy-position="QB"
    data-player-name="Bo Nix"
    data-team-id="10"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>26</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DEN.svg" alt="DEN logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="-11.3%" data-attribute="strength_of_schedule"><span class="column-title">-11.3%</span></td>
        <td class="ds-cell bye centered" data-value="10" data-attribute="player.team.bye"><span class="column-title">10</span></td>
        <td class="ds-cell games-played centered" data-value="13" data-attribute="games_played"><span class="column-title">13</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="150.6" data-attribute="rosWeeklyFloorPts"><span class="column-title">150.6</span></td>
        <td class="ds-cell ros-proj centered" data-value="180.7" data-attribute="rosWeeklyPts"><span class="column-title">180.7</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="210.9" data-attribute="rosWeeklyCeilingPts"><span class="column-title">210.9</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="72.0" data-attribute="dsValue"><span class="column-title">72.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="3" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">3</span></td>
    </tr>
</tbody>

<tbody
    data-player-row
    data-key="99001"
    data-tier-overall="9"
    data-tier-positional="9"
    data-fantasy-position="DEF"
    data-player-name="Denver Broncos"
    data-team-id="10"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>150</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DEN.svg" alt="DEN logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="1.0%" data-attribute="strength_of_schedule"><span class="column-title">1.0%</span></td>
        <td class="ds-cell bye centered" data-value="10" data-attribute="player.team.bye"><span class="column-title">10</span></td>
        <td class="ds-cell games-played centered" data-value="13" data-attribute="games_played"><span class="column-title">13</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="60.0" data-attribute="rosWeeklyFloorPts"><span class="column-title">60.0</span></td>
        <td class="ds-cell ros-proj centered" data-value="80.0" data-attribute="rosWeeklyPts"><span class="column-title">80.0</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="100.0" data-attribute="rosWeeklyCeilingPts"><span class="column-title">100.0</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="20.0" data-attribute="dsValue"><span class="column-title">20.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="0" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">0</span></td>
    </tr>
</tbody>
"""


def test_parses_all_rows_including_non_fantasy_positions():
    rows = _parse_page(REAL_FRAGMENT)
    assert len(rows) == 3  # _parse_page itself does NOT filter positions


def test_first_row_fields():
    row = _parse_page(REAL_FRAGMENT)[0]
    assert row.source_player_id == "13542"
    assert row.player_name == "Jahmyr Gibbs"
    assert row.team == "DET"
    assert row.position == "RB"
    assert row.rank == 1
    assert row.tier_overall == 1
    assert row.tier_positional == 1
    assert row.strength_of_schedule == "-3.9%"
    assert row.bye == 6
    assert row.games_played == 12
    assert row.floor_proj == 180.5
    assert row.projection == 220.4
    assert row.ceiling_proj == 260.1
    assert row.ds_value == 95.0
    assert row.injury_risk == "8"


def test_empty_fragment_returns_no_rows():
    assert _parse_page("<div>no rows here</div>") == []


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    """Returns one fragment per call, then an empty page, recording the
    offset/params each call was made with so pagination can be asserted."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append(params)
        if self.pages:
            return _FakeResponse(self.pages.pop(0))
        return _FakeResponse("")


def test_fetch_paginates_until_empty_page_and_filters_to_offense_positions():
    session = _FakeSession([REAL_FRAGMENT])
    rows = fetch_draftsharks_ros("half-ppr", request_delay=0, session=session)

    # 3 rows in the fragment, but only RB/QB are kept -- DEF is dropped.
    assert len(rows) == 2
    assert {r.position for r in rows} == {"RB", "QB"}

    # First call at offset 0; since the only page returned fewer rows than
    # a full page, fetch stops after one call (no second, empty-page call
    # needed -- same short-circuit draftsharks_weekly.py's fetch uses).
    assert len(session.calls) == 1
    assert session.calls[0]["offset"] == 0
    assert session.calls[0]["fantasyPosition"] == ""
    assert session.calls[0]["pprSuperflexSlug"] == "half-ppr"
```

- [ ] **Step 2: Run it to verify it fails (module doesn't exist yet)**

```bash
python -m pytest tests/test_draftsharks_ros.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.sources.draftsharks_ros'`

- [ ] **Step 3: Write the source module**

Create `src/sources/draftsharks_ros.py`:

```python
"""Draft Sharks rest-of-season (ROS) rankings -- public, unauthenticated
`load-rows` endpoint, same family as weekly-rankings/load-rows
(draftsharks_weekly.py) but a different report: `dsValue` is Draft Sharks'
single blended ROS trade value (their "3D value" score, analogous to
weekly's `weekly3dPts`), and the row shape carries floor/ceiling ROS
projections, games-played-rest-of-season, and injury risk instead of a
single week's matchup/opponent.

Unlike weekly rankings (one `fantasyPosition` per call), this endpoint
returns every position -- offense and IDP/K/DEF -- in one paginated call
per scoring slug when `fantasyPosition` is left blank. This project only
tracks QB/RB/WR/TE, so `fetch_draftsharks_ros` filters non-fantasy
positions out before returning.

See docs/DATA.md for the verified request/response shape.
"""

import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.draftsharks.com/ros-rankings/load-rows"
PAGE_SIZE = 300
USER_AGENT = "Mozilla/5.0 (compatible; in-season-tools/1.0)"
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


class DraftSharksRosFetchError(RuntimeError):
    pass


@dataclass
class DraftSharksRosRow:
    source_player_id: str
    player_name: str
    team: str | None
    position: str
    rank: int | None
    tier_overall: int | None
    tier_positional: int | None
    strength_of_schedule: str | None
    bye: int | None
    games_played: int | None
    floor_proj: float | None       # rosWeeklyFloorPts
    projection: float | None        # rosWeeklyPts
    ceiling_proj: float | None      # rosWeeklyCeilingPts
    ds_value: float | None          # dsValue -- Draft Sharks' blended ROS trade value
    injury_risk: str | None         # player.sipPlayerProfile.injury_prob, raw/unparsed


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_page(html: str) -> list[DraftSharksRosRow]:
    """Parses every `tbody[data-player-row]` block on the page, including
    non-fantasy positions (LB/DL/DB/K/DEF) -- filtering to QB/RB/WR/TE is
    `fetch_draftsharks_ros`'s job, not this function's, so pagination math
    (which depends on the RAW page row count) stays correct."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[DraftSharksRosRow] = []
    for tbody in soup.select("tbody[data-player-row]"):
        cells = {
            td["data-attribute"]: td.get("data-value")
            for td in tbody.select("td[data-attribute]")
        }
        rank_span = tbody.select_one(".rank-index span")
        team_img = tbody.select_one("img.team-badge")
        team = None
        if team_img and team_img.get("src"):
            match = re.search(r"/teams/([A-Z]+)\.svg", team_img["src"])
            if match:
                team = match.group(1)

        rows.append(DraftSharksRosRow(
            source_player_id=tbody.get("data-key", ""),
            player_name=tbody.get("data-player-name", "").strip(),
            team=team,
            position=tbody.get("data-fantasy-position", ""),
            rank=_to_int(rank_span.get_text(strip=True)) if rank_span else None,
            tier_overall=_to_int(tbody.get("data-tier-overall")),
            tier_positional=_to_int(tbody.get("data-tier-positional")),
            strength_of_schedule=cells.get("strength_of_schedule") or None,
            bye=_to_int(cells.get("player.team.bye")),
            games_played=_to_int(cells.get("games_played")),
            floor_proj=_to_float(cells.get("rosWeeklyFloorPts")),
            projection=_to_float(cells.get("rosWeeklyPts")),
            ceiling_proj=_to_float(cells.get("rosWeeklyCeilingPts")),
            ds_value=_to_float(cells.get("dsValue")),
            injury_risk=cells.get("player.sipPlayerProfile.injury_prob") or None,
        ))
    return rows


def fetch_draftsharks_ros(
    scoring_slug: str,
    request_delay: float = 0.5,
    session: requests.Session | None = None,
) -> list[DraftSharksRosRow]:
    """Fetches every QB/RB/WR/TE player's ROS rankings for one scoring
    format, paginating with `offset` until a page returns zero rows (same
    pattern as fetch_draftsharks_weekly), then filtering out non-fantasy
    positions (LB/DL/DB/K/DEF) before returning."""
    sess = session or requests.Session()
    all_rows: list[DraftSharksRosRow] = []
    offset = 0
    while True:
        params = {
            "offset": offset,
            "limit": PAGE_SIZE,
            "fantasyPosition": "",
            "pprSuperflexSlug": scoring_slug,
            "sort": "-dsValue",
            "researchDepth": "rankings",
        }
        try:
            response = sess.get(
                BASE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DraftSharksRosFetchError(
                f"Draft Sharks ROS load-rows request failed at offset={offset}: {exc}"
            ) from exc

        page_rows = _parse_page(response.text)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        offset += len(page_rows)
        if len(page_rows) < PAGE_SIZE:
            break
        time.sleep(request_delay)

    return [r for r in all_rows if r.position in FANTASY_POSITIONS]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_draftsharks_ros.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sources/draftsharks_ros.py tests/test_draftsharks_ros.py
git commit -m "Add Draft Sharks ROS rankings source module"
```

---

## Task 3: Normalize function

**Files:**
- Modify: `src/normalize.py`
- Modify: `tests/test_normalize.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_normalize.py`:

```python
from src.normalize import draftsharks_ros_to_rows
from src.sources.draftsharks_ros import DraftSharksRosRow


def test_draftsharks_ros_to_rows_resolves_canonical_name():
    raw = [DraftSharksRosRow(
        source_player_id="123", player_name="Cam Skattebo", team="NYG",
        position="RB", rank=5, tier_overall=1, tier_positional=1,
        strength_of_schedule="-1.0%", bye=9, games_played=14,
        floor_proj=150.0, projection=180.0, ceiling_proj=210.0,
        ds_value=88.0, injury_risk="5",
    )]
    rows = draftsharks_ros_to_rows(
        raw, season=2026, as_of_week=3, scoring="half-ppr",
        pulled_at="2026-09-16T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Cameron Skattebo"
    assert rows[0].source == "draftsharks"
    assert rows[0].as_of_week == 3
    assert rows[0].ds_value == 88.0
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_normalize.py -v
```
Expected: `ImportError: cannot import name 'draftsharks_ros_to_rows'`

- [ ] **Step 3: Add the function**

In `src/normalize.py`, add this import alongside the existing ones at the top:

```python
from src.schema import RankingRow, RosRankingRow, TradeValueRow
from src.sources.draftsharks_ros import DraftSharksRosRow
```

(This replaces the existing `from src.schema import RankingRow, TradeValueRow` line and adds a new import line for `DraftSharksRosRow` alongside the existing `DraftSharksRow`/`ExpertWeeklyRow` imports.)

Then append this function to the end of `src/normalize.py`:

```python
def draftsharks_ros_to_rows(
    rows: list[DraftSharksRosRow], season: int, as_of_week: int, scoring: str, pulled_at: str,
) -> list[RosRankingRow]:
    return [
        RosRankingRow(
            season=season, source="draftsharks", scoring=scoring,
            pulled_at=pulled_at, as_of_week=as_of_week,
            source_player_id=r.source_player_id, player_name=r.player_name,
            canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
            rank=r.rank, tier_overall=r.tier_overall, tier_positional=r.tier_positional,
            projection=r.projection, floor_proj=r.floor_proj, ceiling_proj=r.ceiling_proj,
            ds_value=r.ds_value, strength_of_schedule=r.strength_of_schedule,
            games_played=r.games_played, injury_risk=r.injury_risk, bye=r.bye,
        )
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_normalize.py -v
```
Expected: all passed (4 tests total)

- [ ] **Step 5: Commit**

```bash
git add src/normalize.py tests/test_normalize.py
git commit -m "Add draftsharks_ros_to_rows normalize function"
```

---

## Task 4: Storage functions

**Files:**
- Modify: `src/storage.py`

No dedicated test file exists for `storage.py` today (its existing functions are exercised indirectly through the pull scripts) — this task follows that precedent and verifies manually instead of adding a new test file.

- [ ] **Step 1: Add the import and two functions**

In `src/storage.py`, change the import line:

```python
from src.schema import LONG_FORMAT_COLUMNS, RankingRow, TRADE_VALUE_COLUMNS, TradeValueRow
```

to:

```python
from src.schema import (
    LONG_FORMAT_COLUMNS, RankingRow, ROS_RANKING_COLUMNS, RosRankingRow,
    TRADE_VALUE_COLUMNS, TradeValueRow,
)
```

Then append to the end of the file:

```python
def ros_raw_snapshot_path(
    raw_dir: Path, source: str, season: int, as_of_week: int, scoring: str, pulled_at: str
) -> Path:
    safe_ts = pulled_at.replace(":", "").replace("-", "")
    return raw_dir / source / str(season) / f"asofweek{as_of_week:02d}_{scoring}_{safe_ts}.json"


def append_ros_rankings_processed(processed_path: Path, rows: list[RosRankingRow]) -> None:
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not processed_path.exists()
    with processed_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ROS_RANKING_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
```

- [ ] **Step 2: Manually verify the round trip**

```bash
python -c "
from pathlib import Path
from src.schema import RosRankingRow
from src.storage import append_ros_rankings_processed
import tempfile, csv

row = RosRankingRow(
    season=2026, source='draftsharks', scoring='half-ppr',
    pulled_at='2026-09-16T00:00:00+00:00', as_of_week=3,
    source_player_id='1', player_name='Test Player', canonical_name='Test Player',
    team='DET', position='RB', rank=1, tier_overall=1, tier_positional=1,
    projection=200.0, floor_proj=150.0, ceiling_proj=250.0, ds_value=90.0,
    strength_of_schedule='-1.0%', games_played=14, injury_risk='5', bye=6,
)
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / 'ros.csv'
    append_ros_rankings_processed(path, [row])
    with path.open(encoding='utf-8') as f:
        print(list(csv.DictReader(f)))
"
```
Expected: prints one dict with all 21 columns and the values above, no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/storage.py
git commit -m "Add ROS rankings storage functions"
```

---

## Task 5: Validation

**Files:**
- Modify: `src/validate.py`
- Create: `tests/test_validate_ros_rankings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validate_ros_rankings.py`:

```python
from src.schema import RosRankingRow
from src.validate import validate_ros_rankings


def make_row(player_name="Player", position="RB", rank=1, source_player_id="1", **kw):
    defaults = dict(
        season=2026, source="draftsharks", scoring="half-ppr",
        pulled_at="2026-09-16T00:00:00+00:00", as_of_week=3,
        source_player_id=source_player_id, player_name=player_name,
        canonical_name=player_name, team="DET", position=position, rank=rank,
        tier_overall=1, tier_positional=1, projection=200.0, floor_proj=150.0,
        ceiling_proj=250.0, ds_value=90.0, strength_of_schedule="-1.0%",
        games_played=14, injury_risk="5", bye=6,
    )
    defaults.update(kw)
    return RosRankingRow(**defaults)


def test_empty_pull_is_an_error():
    issues = validate_ros_rankings([])
    assert any(i.severity == "error" for i in issues)


def test_blank_player_name_is_an_error():
    rows = [make_row(player_name="")]
    issues = validate_ros_rankings(rows)
    assert any(i.severity == "error" for i in issues)


def test_blank_position_is_an_error():
    rows = [make_row(position="")]
    issues = validate_ros_rankings(rows)
    assert any(i.severity == "error" for i in issues)


def test_below_position_floor_is_a_warning_not_an_error():
    rows = [make_row(player_name=f"Player {i}", source_player_id=str(i)) for i in range(3)]
    issues = validate_ros_rankings(rows, position_floors={"RB": 30})
    assert any(i.severity == "warning" for i in issues)
    assert not any(i.severity == "error" for i in issues)


def test_healthy_pull_has_no_issues():
    rows = [
        make_row(player_name=f"Player {i}", source_player_id=str(i), rank=i)
        for i in range(35)
    ]
    issues = validate_ros_rankings(rows, position_floors={"RB": 30})
    assert issues == []
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_validate_ros_rankings.py -v
```
Expected: `ImportError: cannot import name 'validate_ros_rankings'`

- [ ] **Step 3: Add the function**

Append to the end of `src/validate.py`:

```python
def validate_ros_rankings(
    rows: list[RosRankingRow],
    position_floors: dict[str, int] | None = None,
) -> list[ValidationIssue]:
    """Validates one scoring slug's Draft Sharks ROS pull. Mirrors
    validate_pull (all positions pulled in one call, same shape as weekly
    rankings) rather than validate_trade_values (per-position pulls)."""
    if not rows:
        return [ValidationIssue("error", "ROS rankings pull returned zero rows.")]
    issues: list[ValidationIssue] = []
    missing_name = sum(1 for r in rows if not r.player_name)
    missing_position = sum(1 for r in rows if not r.position)
    if missing_name:
        issues.append(ValidationIssue(
            "error", f"{missing_name}/{len(rows)} rows have a blank player_name."
        ))
    if missing_position:
        issues.append(ValidationIssue(
            "error", f"{missing_position}/{len(rows)} rows have a blank position."
        ))
    issues += check_position_counts(rows, position_floors or MINIMUM_POSITION_COUNTS)
    return issues
```

Also add `RosRankingRow` to the existing schema import line near the top of `src/validate.py`:

```python
from src.schema import RankingRow, RosRankingRow, TradeValueRow
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_validate_ros_rankings.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/validate.py tests/test_validate_ros_rankings.py
git commit -m "Add validate_ros_rankings"
```

---

## Task 6: Pull script

**Files:**
- Create: `scripts/pull_draftsharks_ros.py`

No test file — matches the existing precedent (`pull_trade_values.py` and `pull_week.py`'s `main()` also have no direct test; only their extracted pure-function helpers, if any, get unit tests). This script has no such helper to extract (it's a simple loop over 2 scoring slugs), so verification here is a manual smoke test in Step 2.

- [ ] **Step 1: Write the script**

Create `scripts/pull_draftsharks_ros.py`:

```python
#!/usr/bin/env python
"""Pulls Draft Sharks' rest-of-season (ROS) rankings for both scoring
formats and writes them to data/raw/draftsharks_ros/ (immutable snapshot)
and data/processed/ros_rankings_long.csv (append).

Usage:
    python scripts/pull_draftsharks_ros.py                  # both scorings, current week snapshot
    python scripts/pull_draftsharks_ros.py --scoring half-ppr
    python scripts/pull_draftsharks_ros.py --as-of-week 3    # override the snapshot week marker

Exits non-zero only on a validation error or unexpected failure. Writes
data/last_draftsharks_ros_status.json using the same
{run_at, ok, combos: {"week{N}/draftsharks_ros/{scoring}": status}} shape
last_run_status.json already uses, so scheduled_pull.ps1's existing dynamic
source-discovery logic can pick this file up as another source with no
hardcoded label added to the PowerShell script.
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
from src.sources.draftsharks_ros import DraftSharksRosFetchError, fetch_draftsharks_ros

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "ros_rankings_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_draftsharks_ros_status.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=season_config.SEASON)
    parser.add_argument("--scoring", default="half-ppr,ppr", help="Comma list")
    parser.add_argument(
        "--as-of-week", type=int, default=None,
        help="Defaults to the current active week (src/season_config.py).",
    )
    args = parser.parse_args()

    as_of_week = args.as_of_week if args.as_of_week is not None else season_config.current_week()
    scorings = args.scoring.split(",")

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    print(f"Starting Draft Sharks ROS pull -- as-of week {as_of_week}, scorings {scorings}")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    run_status = {}
    any_errors = False
    success_count = 0

    for i, scoring in enumerate(scorings, 1):
        status_key = f"week{as_of_week}/draftsharks_ros/{scoring}"
        print(f"[{i}/{len(scorings)}] {scoring}...")
        try:
            raw = fetch_draftsharks_ros(scoring_slug=scoring)
        except DraftSharksRosFetchError as e:
            print(f"\n[FAILED] {scoring}: {e}")
            any_errors = True
            run_status[status_key] = f"failed: {e}"
            continue
        except Exception as e:
            print(f"\n[FAILED] Unexpected failure on {scoring}: {e}")
            traceback.print_exc()
            run_status[status_key] = f"failed: unexpected error: {e}"
            _write_status(run_status, any_errors=True)
            sys.exit(1)

        rows = normalize.draftsharks_ros_to_rows(raw, args.season, as_of_week, scoring, pulled_at)
        rows, dedupe_issues = validate.dedupe_players(rows)
        issues = dedupe_issues + validate.validate_ros_rankings(rows)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"   [{tag}] {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[status_key] = "failed: " + "; ".join(
                i.message for i in issues if i.severity == "error"
            )
            print(f"   Not writing output for {scoring} -- validation failed.")
            continue

        snapshot_path = storage.ros_raw_snapshot_path(
            RAW_DIR / "draftsharks_ros", "draftsharks", args.season, as_of_week, scoring, pulled_at
        )
        storage.write_raw_snapshot(snapshot_path, raw)
        storage.append_ros_rankings_processed(PROCESSED_PATH, rows)
        run_status[status_key] = "ok"
        success_count += 1
        print(f"   {len(rows)} rows -> {snapshot_path.relative_to(BASE_DIR)}")

    elapsed = datetime.now() - start
    mins, secs = elapsed.seconds // 60, elapsed.seconds % 60
    print(f"\n{'=' * 45}")
    print(f"Done: {success_count}/{len(scorings)} scoring format(s) written")
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
                "combos": run_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test against the live endpoint**

```bash
python scripts/pull_draftsharks_ros.py --scoring half-ppr
```
Expected: prints `[1/1] half-ppr...`, a row count and output path, ends with `Done: 1/1 scoring format(s) written`, exit code 0. Check the printed row count is in the same ballpark as the confirmed sample counts (RB ~81, WR ~77, QB ~33, TE ~26 → roughly 200+ total). If this fails or the row count looks wrong, capture the actual response HTML and compare its `data-attribute` names against `src/sources/draftsharks_ros.py` — the field names in this plan were not verified against a live capture (see the note in `tests/test_draftsharks_ros.py`), so a mismatch here is the most likely first bug, not a logic error.

Then inspect the output:
```bash
python -c "import csv; print(list(csv.DictReader(open('data/processed/ros_rankings_long.csv', encoding='utf-8')))[0])"
```
Expected: a dict with all 21 `ROS_RANKING_COLUMNS`, non-null `projection`/`floor_proj`/`ceiling_proj`/`ds_value` for at least the top rows.

- [ ] **Step 3: Commit**

```bash
git add scripts/pull_draftsharks_ros.py
git commit -m "Add pull_draftsharks_ros.py script"
```

(Do not commit the `data/` output from the smoke test unless the repo already tracks `data/processed/*.csv` — check `git status` first; if `data/` is gitignored, there's nothing to worry about.)

---

## Task 7: Wire into `push_to_supabase.py`

**Files:**
- Modify: `scripts/push_to_supabase.py`
- Modify: `tests/test_push_to_supabase.py`

- [ ] **Step 1: Update the failing test first**

In `tests/test_push_to_supabase.py`, replace `test_state_roundtrip` with:

```python
def test_state_roundtrip(tmp_path, monkeypatch):
    import scripts.push_to_supabase as mod
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", state_path)
    assert _read_state() == {
        "rankings_rows_pushed": 0, "trade_values_rows_pushed": 0,
        "ros_rankings_rows_pushed": 0,
    }
    _write_state({
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    })
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    }
    assert _read_state() == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
        "ros_rankings_rows_pushed": 1,
    }
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_push_to_supabase.py::test_state_roundtrip -v
```
Expected: FAIL — `_read_state()` still returns the old 2-key dict.

- [ ] **Step 3: Update `push_to_supabase.py`**

Add these constants near the top, alongside the existing `RANKINGS_CSV`/`TRADE_VALUES_CSV` etc.:

```python
ROS_RANKINGS_CSV = BASE_DIR / "data" / "processed" / "ros_rankings_long.csv"
ROS_STATUS_PATH = BASE_DIR / "data" / "last_draftsharks_ros_status.json"
```

Add these alongside the existing `RANKINGS_INT_COLS`/`RANKINGS_FLOAT_COLS`/etc.:

```python
ROS_RANKINGS_INT_COLS = {
    "season", "as_of_week", "rank", "tier_overall", "tier_positional",
    "games_played", "bye",
}
ROS_RANKINGS_FLOAT_COLS = {"projection", "floor_proj", "ceiling_proj", "ds_value"}
```

Update `_read_state`'s default:

```python
def _read_state() -> dict:
    if PUSH_STATE_PATH.exists():
        return json.loads(PUSH_STATE_PATH.read_text(encoding="utf-8"))
    return {
        "rankings_rows_pushed": 0, "trade_values_rows_pushed": 0,
        "ros_rankings_rows_pushed": 0,
    }
```

In `main()`, right after `state = _read_state()`, add a backward-compatible default for any already-persisted state file from before this change (the real `data/supabase_push_state.json` on disk today has only the first two keys):

```python
    state = _read_state()
    state.setdefault("ros_rankings_rows_pushed", 0)
    any_failure = False
```

Add a third `_push_new_rows` call right after the existing trade-values one:

```python
    if not _push_new_rows(
        TRADE_VALUES_CSV, "in_season_trade_values", TRADE_INT_COLS, TRADE_FLOAT_COLS,
        state, "trade_values_rows_pushed", base_url, headers,
    ):
        any_failure = True

    if not _push_new_rows(
        ROS_RANKINGS_CSV, "in_season_ros_rankings", ROS_RANKINGS_INT_COLS, ROS_RANKINGS_FLOAT_COLS,
        state, "ros_rankings_rows_pushed", base_url, headers,
    ):
        any_failure = True
```

Add a third tuple to the status-upsert loop:

```python
    for status_path, dataset_prefix, key_field in (
        (RUN_STATUS_PATH, "rankings", "combos"),
        (TRADE_STATUS_PATH, "trade_values", "positions"),
        (ROS_STATUS_PATH, "ros_rankings", "combos"),
    ):
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_push_to_supabase.py -v
```
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add scripts/push_to_supabase.py tests/test_push_to_supabase.py
git commit -m "Push Draft Sharks ROS rankings to Supabase"
```

---

## Task 8: Supabase migration

**Files:**
- Create: `supabase/migrations/0002_ros_rankings.sql`

This creates the migration file locally (a normal, reversible file edit). **Applying it to the live Supabase project is a separate, explicit step in Step 2 below — that project (`tdtchffawcmkvgrccjza`) is shared infrastructure other tools (Vampire, BigBallerLeague) also connect to, so get the user's explicit go-ahead before running it, even though `create table if not exists` is itself non-destructive.**

- [ ] **Step 1: Write the migration file**

Create `supabase/migrations/0002_ros_rankings.sql`:

```sql
-- in-season/supabase/migrations/0002_ros_rankings.sql
create table if not exists in_season_ros_rankings (
  id bigserial primary key,
  season int not null,
  source text not null,
  scoring text not null,
  pulled_at timestamptz not null,
  as_of_week int not null,
  source_player_id text not null,
  player_name text not null,
  canonical_name text not null,
  team text,
  position text not null,
  rank int,
  tier_overall int,
  tier_positional int,
  projection double precision,
  floor_proj double precision,
  ceiling_proj double precision,
  ds_value double precision,
  strength_of_schedule text,
  games_played int,
  injury_risk text,
  bye int,
  created_at timestamptz not null default now()
);

create index if not exists in_season_ros_rankings_lookup_idx
  on in_season_ros_rankings (season, source, scoring, canonical_name);

create or replace view in_season_ros_rankings_latest as
select distinct on (season, source, scoring, canonical_name) *
from in_season_ros_rankings
order by season, source, scoring, canonical_name, pulled_at desc;
```

- [ ] **Step 2: Apply the migration to the live Supabase project (requires explicit confirmation before running)**

Ask the user to confirm before running this — it modifies the shared "Fantasy Football" Supabase project. Once confirmed, apply it with the Supabase MCP tool's `apply_migration` (project id `tdtchffawcmkvgrccjza`, name `ros_rankings`, using the SQL above), or via the Supabase CLI if that's the user's preferred path for this project. After applying, verify with `list_tables` (or `select * from in_season_ros_rankings limit 1;`) that the table and `in_season_ros_rankings_latest` view both exist.

- [ ] **Step 3: Commit the migration file**

```bash
git add supabase/migrations/0002_ros_rankings.sql
git commit -m "Add in_season_ros_rankings Supabase migration"
```

---

## Task 9: Wire into `scheduled_pull.ps1`

**Files:**
- Modify: `scripts/scheduled_pull.ps1`

- [ ] **Step 1: Extend `Get-StatusData` to read the new status file**

In `scripts/scheduled_pull.ps1`, find this block near the top of `Get-StatusData`:

```powershell
    $tvStatus = $null
    $tvDate = $null
    if (Test-Path $tradeValuesStatusPath) {
        $tvStatus = Get-Content $tradeValuesStatusPath -Raw | ConvertFrom-Json
        $tvDate = ([DateTimeOffset]$tvStatus.run_at).ToString("yyyy-MM-dd")
    }
```

Add right after it:

```powershell
    $rosRankingsStatusPath = Join-Path $InSeasonDir "data\last_draftsharks_ros_status.json"
    $rosStatus = $null
    $rosDate = $null
    if (Test-Path $rosRankingsStatusPath) {
        $rosStatus = Get-Content $rosRankingsStatusPath -Raw | ConvertFrom-Json
        $rosDate = ([DateTimeOffset]$rosStatus.run_at).ToString("yyyy-MM-dd")
    }

    # Some source keys don't title-case into a clean display label on their
    # own (e.g. "draftsharks_ros" -> "Draftsharks_Ros") -- override those
    # here instead of hardcoding a branch per source in the loop below.
    $sourceLabelOverrides = @{ "draftsharks_ros" = "Draft Sharks ROS Rankings" }
```

Then find the per-scoring-format loop's source-discovery block:

```powershell
        # Discover weekly-rankings sources dynamically from the combos data
        # (rather than a hardcoded list) so a new source added to
        # pull_week.py's ALL_SOURCES shows up here automatically.
        $sourceNames = @()
        if ($rankingsStatus) {
            foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
                if ($combo.Name -match "^week\d+/([a-zA-Z0-9_-]+)/$([regex]::Escape($key))$") {
                    $sourceNames += $Matches[1]
                }
            }
        }
        $sourceNames = $sourceNames | Sort-Object -Unique

        foreach ($src in $sourceNames) {
            $srcCombo = "week$CurrentWeek/$src/$key"
            $srcValue = if ($rankingsStatus) { $rankingsStatus.combos.$srcCombo } else { $null }
            $srcState = Get-ComboState $srcValue

            $capturedWeeks = @()
            foreach ($combo in $rankingsStatus.combos.PSObject.Properties) {
                if ($combo.Name -match "^week(\d+)/$([regex]::Escape($src))/$([regex]::Escape($key))$" -and $combo.Value -eq "ok") {
                    $capturedWeeks += [int]$Matches[1]
                }
            }
            $capturedWeeks = $capturedWeeks | Sort-Object

            $label = (Get-Culture).TextInfo.ToTitleCase($src)
            $items += @{
                Label = "$label Weekly Rankings"
                State = $srcState
                Date = if ($srcState -eq "ok") { $rankingsDate } else { $null }
                Weeks = $capturedWeeks
            }
        }
```

Replace that entire block with:

```powershell
        # Discover sources dynamically from each status file's own combo
        # keys (rather than a hardcoded list) so a new source added to
        # pull_week.py's ALL_SOURCES -- or a new status file like this one --
        # shows up here automatically. Each status file is looked up back in
        # ITSELF (not cross-matched) since source names are disjoint across
        # files (draftsharks/boone/smythe live in one file, draftsharks_ros
        # in another).
        foreach ($fileEntry in @(
            @{ Status = $rankingsStatus; Date = $rankingsDate }
            @{ Status = $rosStatus; Date = $rosDate }
        )) {
            $status = $fileEntry.Status
            if (-not $status) { continue }

            $sourceNames = @()
            foreach ($combo in $status.combos.PSObject.Properties) {
                if ($combo.Name -match "^week\d+/([a-zA-Z0-9_-]+)/$([regex]::Escape($key))$") {
                    $sourceNames += $Matches[1]
                }
            }
            $sourceNames = $sourceNames | Sort-Object -Unique

            foreach ($src in $sourceNames) {
                $srcCombo = "week$CurrentWeek/$src/$key"
                $srcValue = $status.combos.$srcCombo
                $srcState = Get-ComboState $srcValue

                $capturedWeeks = @()
                foreach ($combo in $status.combos.PSObject.Properties) {
                    if ($combo.Name -match "^week(\d+)/$([regex]::Escape($src))/$([regex]::Escape($key))$" -and $combo.Value -eq "ok") {
                        $capturedWeeks += [int]$Matches[1]
                    }
                }
                $capturedWeeks = $capturedWeeks | Sort-Object

                $label = if ($sourceLabelOverrides.ContainsKey($src)) {
                    $sourceLabelOverrides[$src]
                } else {
                    "$((Get-Culture).TextInfo.ToTitleCase($src)) Weekly Rankings"
                }

                $items += @{
                    Label = $label
                    State = $srcState
                    Date = if ($srcState -eq "ok") { $fileEntry.Date } else { $null }
                    Weeks = $capturedWeeks
                }
            }
        }
```

- [ ] **Step 2: Extend `Send-SuccessEmailIfWarranted`'s first-publish tracking**

Find this block:

```powershell
    if (Test-Path $tradeValuesStatusPath) {
        $tvStatus = Get-Content $tradeValuesStatusPath -Raw | ConvertFrom-Json
        foreach ($pos in $tvStatus.positions.PSObject.Properties) {
            if ($pos.Value -eq "ok") {
                $key = "tradevalue:week${CurrentWeek}:$($pos.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += "trade-values/$($pos.Name)"
                    $state[$key] = "sent"
                }
            }
        }
    }
```

Add right after it (still inside `Send-SuccessEmailIfWarranted`, before `Save-NotifyState $state`):

```powershell
    $rosRankingsStatusPath = Join-Path $InSeasonDir "data\last_draftsharks_ros_status.json"
    if (Test-Path $rosRankingsStatusPath) {
        $rosStatus = Get-Content $rosRankingsStatusPath -Raw | ConvertFrom-Json
        foreach ($combo in $rosStatus.combos.PSObject.Properties) {
            if ($combo.Value -eq "ok") {
                $key = "rosrankings:$($combo.Name)"
                if (-not $state.ContainsKey($key)) {
                    $newlyPublished += "ros-rankings/$($combo.Name)"
                    $state[$key] = "sent"
                }
            }
        }
    }
```

- [ ] **Step 3: Add the pull step to the main script body**

Find:

```powershell
    Log "Running pull_trade_values.py..."
    & $PythonExe "scripts\pull_trade_values.py" 2>&1 | ForEach-Object { Log $_ }
    $tradeValuesExit = $LASTEXITCODE
    Log "pull_trade_values.py exit code: $tradeValuesExit"

    Log "Running push_to_supabase.py..."
```

Replace with:

```powershell
    Log "Running pull_trade_values.py..."
    & $PythonExe "scripts\pull_trade_values.py" 2>&1 | ForEach-Object { Log $_ }
    $tradeValuesExit = $LASTEXITCODE
    Log "pull_trade_values.py exit code: $tradeValuesExit"

    Log "Running pull_draftsharks_ros.py..."
    & $PythonExe "scripts\pull_draftsharks_ros.py" 2>&1 | ForEach-Object { Log $_ }
    $rosRankingsExit = $LASTEXITCODE
    Log "pull_draftsharks_ros.py exit code: $rosRankingsExit"

    Log "Running push_to_supabase.py..."
```

- [ ] **Step 4: Include the new exit code in failure detection and reporting**

Find:

```powershell
    $anyFailure = ($pullExit -ne 0) -or ($tradeValuesExit -ne 0)
    if ($anyFailure) {
        Log "=== FINISHED WITH FAILURES -- see above / status JSON files ==="
        $failedParts = @()
        if ($pullExit -ne 0) { $failedParts += "pull_week.py exited $pullExit" }
        if ($tradeValuesExit -ne 0) { $failedParts += "pull_trade_values.py exited $tradeValuesExit" }
```

Replace with:

```powershell
    $anyFailure = ($pullExit -ne 0) -or ($tradeValuesExit -ne 0) -or ($rosRankingsExit -ne 0)
    if ($anyFailure) {
        Log "=== FINISHED WITH FAILURES -- see above / status JSON files ==="
        $failedParts = @()
        if ($pullExit -ne 0) { $failedParts += "pull_week.py exited $pullExit" }
        if ($tradeValuesExit -ne 0) { $failedParts += "pull_trade_values.py exited $tradeValuesExit" }
        if ($rosRankingsExit -ne 0) { $failedParts += "pull_draftsharks_ros.py exited $rosRankingsExit" }
```

- [ ] **Step 5: Propagate the new exit code at the end of the script**

Find the final two lines:

```powershell
if ($pullExit -ne 0) { exit $pullExit }
exit $tradeValuesExit
```

Replace with:

```powershell
if ($pullExit -ne 0) { exit $pullExit }
if ($tradeValuesExit -ne 0) { exit $tradeValuesExit }
exit $rosRankingsExit
```

- [ ] **Step 6: Syntax-check the script (without executing it — it makes real network calls)**

```powershell
powershell -NoProfile -Command "$null = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw 'scripts\scheduled_pull.ps1'), [ref]$null); Write-Output 'syntax ok'"
```
Expected: `syntax ok`, no errors printed.

- [ ] **Step 7: Commit**

```bash
git add scripts/scheduled_pull.ps1
git commit -m "Wire Draft Sharks ROS pull into scheduled_pull.ps1 and its status email"
```

---

## Task 10: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/DATA.md`

- [ ] **Step 1: Update `README.md`'s Sources section**

In `README.md`, find the Sources bullet list and add a new bullet after the "Justin Boone rest-of-season trade values" one:

```markdown
- **Draft Sharks rest-of-season (ROS) rankings** — a separate report from
  weekly rankings (`ros-rankings/load-rows`, still public/unauthenticated),
  carrying Draft Sharks' own blended ROS trade value (`ds_value`) plus
  ROS floor/ceiling projections, strength of schedule, games-played, and
  injury risk. Pulled all-positions-in-one-call per scoring format (unlike
  weekly, which is one call per position) — see
  `src/sources/draftsharks_ros.py`. Stored separately from both weekly
  rankings and Boone's trade values, in its own `in_season_ros_rankings`
  table, since neither existing shape fits: it needs floor/ceiling/SOS
  columns weekly's trade-value table doesn't have, and it isn't a
  per-week-published report the way weekly rankings are.
```

Update the Storage section's Supabase bullet:

```markdown
- **Supabase** ("Fantasy Football" project, `tdtchffawcmkvgrccjza` — same
  project Vampire and BigBallerLeague use) — `in_season_rankings`,
  `in_season_trade_values`, `in_season_ros_rankings`, `in_season_pull_status`
  tables, pushed incrementally by `scripts/push_to_supabase.py` (wired into
  `scripts/scheduled_pull.ps1`, runs after every pull). A push failure doesn't
  fail the scheduled run or lose data — the local CSV already has it, and the
  next run retries from a persisted watermark
  (`data/supabase_push_state.json`). See `docs/DATA.md` for the exact schema.
```

Update the Scheduled runs section's first sentence:

```markdown
`scripts/scheduled_pull.ps1` is the Windows Task Scheduler entry point — runs
`pull_week.py`, `pull_trade_values.py`, `pull_draftsharks_ros.py`, the
Supabase push, and the Vampire weekly-projection refresh, with a
network-readiness wait for wake-from-sleep races.
```

- [ ] **Step 2: Add a new section to `docs/DATA.md`**

In `docs/DATA.md`, add this new section right after the "Draft Sharks weekly rankings" section (before "Justin Boone"):

```markdown
## Draft Sharks ROS rankings (`src/sources/draftsharks_ros.py`)

`GET https://www.draftsharks.com/ros-rankings/load-rows` — public,
unauthenticated, same `tbody[data-player-row]` HTML-fragment shape as
weekly rankings, but a **different report**: rest-of-season rankings, not
one week's. Confirmed via browser network inspection (no live capture
saved yet — the fixture in `tests/test_draftsharks_ros.py` is constructed
from the confirmed field names, not a byte-for-byte capture; verify against
a real response the first time this runs and update the fixture if
anything drifts).

**Query params**: same shape as weekly (`offset`, `limit`,
`pprSuperflexSlug`, `researchDepth=rankings`), but no `week` param (this
report isn't week-scoped), `fantasyPosition=""` returns **every** position
in one paginated pull (confirmed one sample page: RB 81, WR 77, QB 33,
TE 26, plus LB/DL/DB/K/DEF — `fetch_draftsharks_ros` filters to
QB/RB/WR/TE), `sort=-dsValue` (this report's default sort, unlike weekly's
`-weekly3dPts`).

**New `data-attribute` cells this report has that weekly doesn't**:
`rosWeeklyPts` (ROS points projection), `rosWeeklyFloorPts`,
`rosWeeklyCeilingPts`, `dsValue` (Draft Sharks' blended ROS trade value —
their "3D value" analog for this report), `games_played` (projected games
played rest of season), `player.sipPlayerProfile.injury_prob` (injury risk
— **format unconfirmed**, stored as raw text in `RosRankingRow.injury_risk`
rather than parsed, pending a live sample).
```

Update the "Supabase shape" section's intro sentence and table list:

```markdown
Live in the "Fantasy Football" Supabase project (`tdtchffawcmkvgrccjza` — same
project Vampire and BigBallerLeague use). Pushed incrementally after every
pull by `scripts/push_to_supabase.py`; local files remain the source of
truth, Supabase is a secondary copy. Four tables — the three ranking/value
tables are append-only for the same reason the local CSVs are: a new
`pulled_at` for the same logical row is a new row, never an overwrite, so
re-pulling a not-yet-played week to catch DraftSharks' mid-week updates
preserves the full history Jared asked for. The fourth (`in_season_pull_status`)
is a small mutable status table, one row per dataset:
```

Add a new bullet after the `in_season_trade_values` one:

```markdown
- **`in_season_ros_rankings`** — mirrors `RosRankingRow`: `season, source,
  scoring, pulled_at, as_of_week, source_player_id, player_name,
  canonical_name, team, position, rank, tier_overall, tier_positional,
  projection, floor_proj, ceiling_proj, ds_value, strength_of_schedule,
  games_played, injury_risk, bye`, plus `id` and `created_at`. Indexed on
  `(season, source, scoring, canonical_name)`. `as_of_week` is a snapshot
  marker only, not part of the latest-view's key (see below) — ROS
  rankings describe the rest of the season, not one specific week.
```

Update the "Two views" paragraph:

```markdown
Three views, each `select distinct on (...) ... order by ..., pulled_at desc`
over their base table — i.e. "latest pull per logical key" without the
caller having to write that query themselves: `in_season_rankings_latest`
(keyed on `season, week, source, scoring, canonical_name`),
`in_season_trade_values_latest` (keyed on `season, week, source, position,
canonical_name`), and `in_season_ros_rankings_latest` (keyed on `season,
source, scoring, canonical_name` — deliberately **without** `as_of_week`,
unlike the other two views' `week`, since "latest" for a ROS row means the
most recent snapshot regardless of which week it was captured in).
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/DATA.md
git commit -m "Document Draft Sharks ROS rankings pipeline"
```

---

## Task 11: Full test suite sanity check

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

```bash
python -m pytest tests/ -v
```
Expected: all tests pass, including every test added in Tasks 2–7 and every pre-existing test (nothing in this plan should have touched `RankingRow`, `TradeValueRow`, or any existing function's behavior).

- [ ] **Step 2: If Task 6's live smoke test hasn't run yet, run it now**

```bash
python scripts/pull_draftsharks_ros.py
```
Expected: exit code 0, `data/last_draftsharks_ros_status.json` shows `"ok": true` with both `half-ppr` and `ppr` combos `"ok"`.

---

## Self-Review Notes

- **Spec coverage:** every numbered item in the design spec (module, schema, storage, validation, script, Supabase table + view, `push_to_supabase.py` wiring, `scheduled_pull.ps1` wiring + email, docs) has a corresponding task above. The design's explicit "out of scope" items (site UI, value-blending, injury-risk normalization) have no task, correctly.
- **Placeholder scan:** no TBD/TODO left; the one deliberately-unverified item (the `injury_prob` format, and the fact that the parsing fixture is constructed rather than captured live) is called out explicitly in Task 2's test docstring, Task 6 Step 2's smoke-test guidance, and Task 10's DATA.md text — a known-and-flagged gap, not a hidden one, matching the design spec's own "Out of scope" note.
- **Type/name consistency check:** `RosRankingRow` / `ROS_RANKING_COLUMNS` / `draftsharks_ros_to_rows` / `validate_ros_rankings` / `ros_raw_snapshot_path` / `append_ros_rankings_processed` / `fetch_draftsharks_ros` / `DraftSharksRosRow` / `DraftSharksRosFetchError` are spelled identically everywhere they're referenced across Tasks 1–9 (schema → source module → normalize → storage → validate → script → push_to_supabase → migration → PowerShell status-file key names `draftsharks_ros`/`week{N}/draftsharks_ros/{scoring}`).
