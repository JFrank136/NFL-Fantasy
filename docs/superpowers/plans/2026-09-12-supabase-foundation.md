# Supabase Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Supabase data layer and shared player-identity system that every future in-season site page will read from, and prep the `team-analyzer` scaffold to become that site's root.

**Architecture:** Python pipeline scripts in `in-season/` compute a `canonical_name` for every row at ingestion (in `src/normalize.py`, via a new `src/player_identity.py`), write it through the existing local CSVs, then push it to three new tables in the existing "Fantasy Football" Supabase project (`tdtchffawcmkvgrccjza`). A new `scripts/push_to_supabase.py` is wired into the existing `scheduled_pull.ps1` automation. `in-season/team-analyzer` is renamed to `in-season/site`, stripped of its stale scraper scaffolding, and prepped for GitHub + Vercel hosting.

**Tech Stack:** Python 3.11, `requests` (already a dependency — no new Python packages), Postgres/Supabase (via the Supabase MCP tools for schema DDL, and PostgREST via `requests` for data), PowerShell 5.1, Vite + React + TS (existing site scaffold, untouched internals).

**Spec:** `docs/superpowers/specs/2026-09-12-supabase-foundation-design.md`

**Deviation from spec, discovered during planning:** the spec assumed `Draft/data/aliases.csv`'s `source` column could be used to scope alias lookups the way `Draft/src/matching.py` does. It can't — that column holds the *site that spelled a name a certain way* (`yahoo`, `footballguys`), never in-season's own sources (`draftsharks`, `boone`, `smythe`), so a source-scoped lookup would never match anything for this pipeline. `player_identity.py` (Task 2) instead matches on normalized name alone, ignoring source/team. One consequence: the spec's "log every unmatched name" idea would now fire for nearly every ordinary player (only ~20 special-case aliases exist total) and add no signal, so it's dropped — `canonical_name_for()` returning the bare normalized name for a non-aliased player is the normal, expected case, not a gap worth logging.

---

### Task 1: Supabase schema — tables and views

No new files for this task's main action (uses the Supabase MCP tool directly), but the SQL is also saved for history.

**Files:**
- Create: `in-season/supabase/migrations/0001_in_season_foundation.sql`

- [ ] **Step 1: Write the migration SQL to a tracked file**

```sql
-- in-season/supabase/migrations/0001_in_season_foundation.sql
create table if not exists in_season_rankings (
  id bigserial primary key,
  season int not null,
  week int not null,
  source text not null,
  scoring text not null,
  pulled_at timestamptz not null,
  source_player_id text not null,
  player_name text not null,
  canonical_name text not null,
  team text,
  position text not null,
  rank int,
  projection double precision,
  floor_proj double precision,
  ceiling_proj double precision,
  tier int,
  bye int,
  opponent text,
  created_at timestamptz not null default now()
);

create index if not exists in_season_rankings_lookup_idx
  on in_season_rankings (season, week, source, scoring, canonical_name);

create table if not exists in_season_trade_values (
  id bigserial primary key,
  season int not null,
  week int not null,
  source text not null,
  position text not null,
  pulled_at timestamptz not null,
  source_url text not null,
  rank int,
  player_name text not null,
  canonical_name text not null,
  team text,
  value_col1_label text not null,
  value_col1 double precision,
  value_col2_label text not null,
  value_col2 double precision,
  created_at timestamptz not null default now()
);

create index if not exists in_season_trade_values_lookup_idx
  on in_season_trade_values (season, week, source, position, canonical_name);

create table if not exists in_season_pull_status (
  dataset text primary key,
  last_success_at timestamptz,
  last_attempt_at timestamptz not null,
  status text not null,
  message text,
  row_count int
);

create or replace view in_season_rankings_latest as
select distinct on (season, week, source, scoring, canonical_name) *
from in_season_rankings
order by season, week, source, scoring, canonical_name, pulled_at desc;

create or replace view in_season_trade_values_latest as
select distinct on (season, week, source, position, canonical_name) *
from in_season_trade_values
order by season, week, source, position, canonical_name, pulled_at desc;
```

- [ ] **Step 2: Apply it to the live Supabase project**

Use the Supabase MCP tool (project id `tdtchffawcmkvgrccjza`, the "Fantasy Football" project — confirm with `list_projects` if this ever changes):

```
apply_migration(
  project_id="tdtchffawcmkvgrccjza",
  name="in_season_foundation",
  query=<the SQL from Step 1>
)
```

- [ ] **Step 3: Verify the tables exist**

```
list_tables(project_id="tdtchffawcmkvgrccjza", schemas=["public"], verbose=false)
```

Expected: `in_season_rankings`, `in_season_trade_values`, `in_season_pull_status` appear alongside the existing `vampire_*` tables, each with `rls_enabled: false` (matches the existing `vampire_*` tables — same accepted low-stakes/no-login tradeoff, not a new issue to fix here).

- [ ] **Step 4: Commit the migration file**

```bash
cd "in-season"
git add supabase/migrations/0001_in_season_foundation.sql
git commit -m "Add Supabase schema for in-season rankings, trade values, and pull status"
```

---

### Task 2: Player identity module

**Files:**
- Create: `in-season/src/player_identity.py`
- Test: `in-season/tests/test_player_identity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_player_identity.py
from src.player_identity import canonical_name_for, load_aliases, normalize_name


def test_normalize_name_lowercases_strips_punctuation_and_hyphens():
    assert normalize_name("D.K. Metcalf") == "dk metcalf"
    assert normalize_name("Cam Skattebo") == "cam skattebo"
    assert normalize_name("Ray-Ray McCloud") == "ray ray mccloud"


def test_normalize_name_drops_generational_suffix():
    assert normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert normalize_name("Kenneth Walker III") == "kenneth walker"


def test_canonical_name_for_uses_provided_alias_table():
    aliases = {"cam skattebo": "Cameron Skattebo"}
    assert canonical_name_for("Cam Skattebo", aliases=aliases) == "Cameron Skattebo"


def test_canonical_name_for_falls_back_to_normalized_name_when_no_alias():
    assert canonical_name_for("Some Rookie", aliases={}) == "some rookie"


def test_load_aliases_reads_the_real_draft_aliases_file():
    # Regression test for the exact players Jared flagged as historically
    # falling through name matching -- confirms this file's real content
    # resolves them once matching ignores source/team (see plan header).
    aliases = load_aliases()
    assert aliases["cam skattebo"] == "Cameron Skattebo"
    assert aliases["kenny gainwell"] == "Kenneth Gainwell"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "in-season"
python -m pytest tests/test_player_identity.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.player_identity'`

- [ ] **Step 3: Write the implementation**

```python
# src/player_identity.py
"""Resolves a canonical player name for rows the in-season pipeline ingests.

Uses Draft/data/aliases.csv as the alias source of truth (the same file
Draft/src/matching.py and Vampire's src/name-matching.js already read
independently). That file is keyed by (raw_name, raw_team, source) where
`source` means the SITE that spelled a name a certain way ("yahoo",
"footballguys") -- not a fantasy-analyst source. None of in-season's own
sources (draftsharks, boone, smythe) ever appear in that column, so a
source-scoped lookup would never match anything here. Matching instead
ignores source/team entirely and keys purely on normalized name -- the file
is small (~20 rows) and curated, so name-only collisions aren't a practical
risk.

This does not fully solve cross-dataset name-matching gaps (e.g. a player
missing entirely from one source's pull) -- seeing docs/superpowers/specs/
2026-09-12-supabase-foundation-design.md for what's explicitly out of scope.
"""

import csv
from pathlib import Path

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "Draft" / "data" / "aliases.csv"

_aliases_cache: dict[str, str] | None = None


def normalize_name(raw_name: str) -> str:
    name = raw_name.lower().strip()
    name = name.replace(".", "").replace("'", "").replace("-", " ")
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens)


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, str]:
    """normalized raw_name -> canonical_name, deduped across all rows
    regardless of source/team (see module docstring for why)."""
    aliases: dict[str, str] = {}
    if not path.exists():
        return aliases
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aliases[normalize_name(row["raw_name"])] = row["canonical_name"]
    return aliases


def canonical_name_for(raw_name: str, aliases: dict[str, str] | None = None) -> str:
    """Resolves `raw_name` to its canonical form. Uses the cached real
    aliases.csv by default; pass `aliases` explicitly in tests to avoid
    depending on that file's live content."""
    global _aliases_cache
    if aliases is None:
        if _aliases_cache is None:
            _aliases_cache = load_aliases()
        aliases = _aliases_cache
    norm = normalize_name(raw_name)
    return aliases.get(norm, norm)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_player_identity.py -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/player_identity.py tests/test_player_identity.py
git commit -m "Add player_identity module for canonical name resolution"
```

---

### Task 3: Add `canonical_name` to the row schemas

**Files:**
- Modify: `in-season/src/schema.py`
- Modify: `in-season/tests/test_validate.py` (existing `make_row` helper — will break without this)
- Modify: `in-season/tests/test_validate_trade_values.py` (existing `make_row` helper — will break without this)

- [ ] **Step 1: Update `RankingRow` and `LONG_FORMAT_COLUMNS`**

In `src/schema.py`, replace the `LONG_FORMAT_COLUMNS` list and `RankingRow` class:

```python
LONG_FORMAT_COLUMNS = [
    "season", "week", "source", "scoring", "pulled_at",
    "source_player_id", "player_name", "canonical_name", "team", "position",
    "rank", "projection", "floor_proj", "ceiling_proj", "tier",
    "bye", "opponent",
]


@dataclass
class RankingRow:
    season: int
    week: int
    source: str          # "draftsharks" | "boone" | "smythe"
    scoring: str          # "half-ppr" | "ppr"
    pulled_at: str         # ISO 8601 timestamp, UTC
    source_player_id: str
    player_name: str
    canonical_name: str
    team: str | None
    position: str
    rank: int | None
    projection: float | None
    floor_proj: float | None = None
    ceiling_proj: float | None = None
    tier: int | None = None
    bye: int | None = None
    opponent: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in LONG_FORMAT_COLUMNS}
```

- [ ] **Step 2: Update `TradeValueRow` and `TRADE_VALUE_COLUMNS`**

```python
TRADE_VALUE_COLUMNS = [
    "season", "week", "source", "position", "pulled_at", "source_url",
    "rank", "player_name", "canonical_name", "team", "value_col1_label",
    "value_col1", "value_col2_label", "value_col2",
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
    canonical_name: str
    team: str | None          # not present in the source table -- always None today
    value_col1_label: str      # e.g. "HALF" (RB/WR/TE) or "1QB" (QB)
    value_col1: float | None
    value_col2_label: str      # e.g. "PPR" (RB/WR/TE) or "2QB" (QB)
    value_col2: float | None

    def as_dict(self) -> dict:
        d = asdict(self)
        return {col: d[col] for col in TRADE_VALUE_COLUMNS}
```

The trailing `assert [f.name for f in fields(...)] == ...` lines at the bottom of the file need no changes — they already check against the updated column lists.

- [ ] **Step 2: Fix the existing test helpers that construct these rows directly**

In `tests/test_validate.py`, update `make_row`'s `defaults` dict to include the new required field:

```python
def make_row(player_name="Player", position="RB", rank=1, source_player_id="1", **kw):
    defaults = dict(
        season=2026, week=1, source="draftsharks", scoring="half-ppr",
        pulled_at="2026-09-08T00:00:00+00:00", source_player_id=source_player_id,
        player_name=player_name, canonical_name=player_name, team="DET",
        position=position, rank=rank, projection=15.0,
    )
    defaults.update(kw)
```

In `tests/test_validate_trade_values.py`, update `make_row`'s `defaults` dict the same way:

```python
def make_row(player_name="Player", rank=1, **kw):
    defaults = dict(
        season=2026, week=1, source="boone", position="RB",
        pulled_at="2026-09-11T00:00:00+00:00",
        source_url="https://sports.yahoo.com/fantasy/article/x.html",
        rank=rank, player_name=player_name, canonical_name=player_name, team=None,
        value_col1_label="HALF", value_col1=50.0,
        value_col2_label="PPR", value_col2=55.0,
    )
    defaults.update(kw)
```

- [ ] **Step 3: Run the full existing test suite to confirm nothing else broke**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS (including `test_validate.py`, `test_validate_trade_values.py`, and Task 2's `test_player_identity.py`). `test_pull_week.py`, `test_boone_trade_values.py`, `test_draftsharks_weekly.py`, `test_yahoo_weekly_consensus.py`, `test_season_config.py` should be unaffected since they don't construct `RankingRow`/`TradeValueRow` directly.

- [ ] **Step 4: Commit**

```bash
git add src/schema.py tests/test_validate.py tests/test_validate_trade_values.py
git commit -m "Add canonical_name field to RankingRow and TradeValueRow"
```

---

### Task 4: Wire canonical name resolution into `normalize.py`

**Files:**
- Modify: `in-season/src/normalize.py`
- Create: `in-season/tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_normalize.py
from src.normalize import (
    boone_trade_values_to_rows,
    draftsharks_to_ranking_rows,
    yahoo_expert_to_ranking_rows,
)
from src.sources.boone_trade_values import TradeValueTableRow
from src.sources.draftsharks_weekly import DraftSharksRow
from src.sources.yahoo_weekly_consensus import ExpertWeeklyRow


def test_draftsharks_to_ranking_rows_resolves_canonical_name():
    raw = [DraftSharksRow(
        source_player_id="123", player_name="Cam Skattebo", team="NYG",
        position="RB", rank=5, matchup="@KC", strength_of_schedule="-1.0%",
        bye=9, floor_proj=8.0, consensus_proj=12.0, ds_proj=11.0,
        ceiling_proj=16.0, three_d_proj=12.5, tier_overall=1,
        tier_positional=1, is_rookie=False,
    )]
    rows = draftsharks_to_ranking_rows(
        raw, season=2026, week=2, scoring="half-ppr",
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Cameron Skattebo"


def test_yahoo_expert_to_ranking_rows_falls_back_to_normalized_name_when_no_alias():
    raw = [ExpertWeeklyRow(
        source_player_id="9", player_name="Some Rookie", team="DAL",
        position="WR", rank=40, bye=7, opponent="vs. PHI",
    )]
    rows = yahoo_expert_to_ranking_rows(
        raw, source="boone", season=2026, week=2, scoring="ppr",
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "some rookie"


def test_boone_trade_values_to_rows_resolves_canonical_name():
    raw = [TradeValueTableRow(
        rank=3, player_name="Kenny Gainwell", value_col1_label="HALF",
        value_col1=14.2, value_col2_label="PPR", value_col2=15.9,
    )]
    rows = boone_trade_values_to_rows(
        "RB", "https://example.com", raw, season=2026, week=2,
        pulled_at="2026-09-12T00:00:00+00:00",
    )
    assert rows[0].canonical_name == "Kenneth Gainwell"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_normalize.py -v
```

Expected: FAIL with `TypeError: RankingRow.__init__() missing 1 required positional argument: 'canonical_name'` (or similar for `TradeValueRow`)

- [ ] **Step 3: Update `normalize.py`**

```python
# src/normalize.py
"""Maps each source's raw row shape into the one shared RankingRow schema."""

from src.player_identity import canonical_name_for
from src.schema import RankingRow, TradeValueRow
from src.sources.boone_trade_values import TradeValueTableRow
from src.sources.draftsharks_weekly import DraftSharksRow
from src.sources.yahoo_weekly_consensus import ExpertWeeklyRow


def draftsharks_to_ranking_rows(
    rows: list[DraftSharksRow], season: int, week: int, scoring: str, pulled_at: str
) -> list[RankingRow]:
    return [
        RankingRow(
            season=season, week=week, source="draftsharks", scoring=scoring,
            pulled_at=pulled_at, source_player_id=r.source_player_id,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
            rank=r.rank, projection=r.three_d_proj, floor_proj=r.floor_proj,
            ceiling_proj=r.ceiling_proj, tier=r.tier_overall, bye=r.bye,
            opponent=r.matchup,
        )
        for r in rows
    ]


def yahoo_expert_to_ranking_rows(
    rows: list[ExpertWeeklyRow], source: str, season: int, week: int, scoring: str,
    pulled_at: str,
) -> list[RankingRow]:
    """`source` is "boone" or "smythe" -- Yahoo's fanPro endpoint doesn't
    return a per-expert numeric projection, only a rank, so `projection`
    stays None for these rows (unlike Draft Sharks, which does have one)."""
    return [
        RankingRow(
            season=season, week=week, source=source, scoring=scoring,
            pulled_at=pulled_at, source_player_id=r.source_player_id,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=r.team, position=r.position,
            rank=r.rank, projection=None, bye=r.bye, opponent=r.opponent,
        )
        for r in rows
    ]


def boone_trade_values_to_rows(
    position: str, source_url: str, table_rows: list[TradeValueTableRow],
    season: int, week: int, pulled_at: str,
) -> list[TradeValueRow]:
    return [
        TradeValueRow(
            season=season, week=week, source="boone", position=position,
            pulled_at=pulled_at, source_url=source_url, rank=r.rank,
            player_name=r.player_name, canonical_name=canonical_name_for(r.player_name),
            team=None,
            value_col1_label=r.value_col1_label, value_col1=r.value_col1,
            value_col2_label=r.value_col2_label, value_col2=r.value_col2,
        )
        for r in table_rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_normalize.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite again**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/normalize.py tests/test_normalize.py
git commit -m "Resolve canonical_name for every row in normalize.py"
```

---

### Task 5: Migrate existing local CSVs to the new column

The processed CSVs already have data (since 2026-09-08) written with the old header (no `canonical_name`). `storage.py` only writes a CSV header when the file doesn't exist yet, so the next pipeline run would otherwise append rows with one more column than the file's existing header declares, misaligning every reader. This is a one-time fix, run once, not part of the ongoing pipeline. (`data/processed/` is gitignored, so this doesn't need a git commit — it's a local data mutation.)

**Files:**
- Create: `in-season/scripts/migrate_csv_add_canonical_name.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python
"""One-time migration: adds a canonical_name column to the existing
processed CSVs, which were written before RankingRow/TradeValueRow gained
that field. Run this once, right after Task 4 lands and before the next
pipeline run -- otherwise the next append writes rows with one more column
than the existing header declares.

Usage:
    python scripts/migrate_csv_add_canonical_name.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.player_identity import canonical_name_for
from src.schema import LONG_FORMAT_COLUMNS, TRADE_VALUE_COLUMNS

BASE_DIR = Path(__file__).resolve().parent.parent
RANKINGS_CSV = BASE_DIR / "data" / "processed" / "rankings_long.csv"
TRADE_VALUES_CSV = BASE_DIR / "data" / "processed" / "trade_values_long.csv"


def migrate(path: Path, columns: list[str]) -> None:
    if not path.exists():
        print(f"{path} does not exist -- nothing to migrate.")
        return
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "canonical_name" in reader.fieldnames:
            print(f"{path} already has canonical_name -- skipping.")
            return
        rows = list(reader)

    for row in rows:
        row["canonical_name"] = canonical_name_for(row["player_name"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Migrated {len(rows)} row(s) in {path}.")


if __name__ == "__main__":
    migrate(RANKINGS_CSV, LONG_FORMAT_COLUMNS)
    migrate(TRADE_VALUES_CSV, TRADE_VALUE_COLUMNS)
```

- [ ] **Step 2: Run it**

```bash
python scripts/migrate_csv_add_canonical_name.py
```

Expected output: `Migrated N row(s) in .../rankings_long.csv` and the same for `trade_values_long.csv`.

- [ ] **Step 3: Verify the header changed**

```bash
python -c "print(open('data/processed/rankings_long.csv', encoding='utf-8').readline())"
```

Expected: header line includes `canonical_name` between `player_name` and `team`.

- [ ] **Step 4: Commit the script (not the CSVs — those are gitignored)**

```bash
git add scripts/migrate_csv_add_canonical_name.py
git commit -m "Add one-time CSV migration script for canonical_name column"
```

---

### Task 6: `push_to_supabase.py`

**Files:**
- Create: `in-season/scripts/push_to_supabase.py`
- Create: `in-season/.env.example`
- Test: `in-season/tests/test_push_to_supabase.py`

- [ ] **Step 1: Write the failing tests (pure-logic helpers only — network calls are verified manually in Step 6, not mocked here)**

```python
# tests/test_push_to_supabase.py
import json

from scripts.push_to_supabase import _coerce_row, _read_new_rows, _read_state, _write_state


def test_coerce_row_converts_int_and_float_columns_and_leaves_blanks_as_none():
    row = {"season": "2026", "week": "2", "rank": "", "projection": "12.5", "player_name": "X"}
    out = _coerce_row(row, int_cols={"season", "week", "rank"}, float_cols={"projection"})
    assert out == {"season": 2026, "week": 2, "rank": None, "projection": 12.5, "player_name": "X"}


def test_read_new_rows_skips_already_pushed_rows(tmp_path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
    rows = _read_new_rows(csv_path, already_pushed=1)
    assert rows == [{"a": "3", "b": "4"}, {"a": "5", "b": "6"}]


def test_read_new_rows_returns_empty_list_for_missing_file(tmp_path):
    assert _read_new_rows(tmp_path / "missing.csv", already_pushed=0) == []


def test_state_roundtrip(tmp_path, monkeypatch):
    import scripts.push_to_supabase as mod
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(mod, "PUSH_STATE_PATH", state_path)
    assert _read_state() == {"rankings_rows_pushed": 0, "trade_values_rows_pushed": 0}
    _write_state({"rankings_rows_pushed": 5, "trade_values_rows_pushed": 2})
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "rankings_rows_pushed": 5, "trade_values_rows_pushed": 2,
    }
    assert _read_state() == {"rankings_rows_pushed": 5, "trade_values_rows_pushed": 2}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_push_to_supabase.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.push_to_supabase'`

- [ ] **Step 3: Create `scripts/__init__.py` if it doesn't already exist (needed so `scripts.push_to_supabase` is importable from tests)**

```bash
python -c "import pathlib; p = pathlib.Path('scripts/__init__.py'); p.exists() or p.write_text('')"
```

- [ ] **Step 4: Write the implementation**

```python
#!/usr/bin/env python
"""Pushes newly-pulled rows from the local processed CSVs into Supabase, and
upserts the latest pull-status snapshot. Called by scheduled_pull.ps1 after
each pull; also safe to run by hand.

Only pushes rows appended since the last successful push (tracked by row
count in data/supabase_push_state.json) -- the CSVs are append-only, so a
simple "rows pushed so far" watermark avoids re-inserting already-pushed
history every run. A push failure here does NOT mean data was lost: the
local CSV already has it, and the watermark stays put so the same unpushed
rows get retried next run.

Usage:
    python scripts/push_to_supabase.py
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, either in the
environment or in in-season/.env (see .env.example) -- this script loads
.env itself so scheduled_pull.ps1 doesn't need to export anything.
"""
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
RANKINGS_CSV = BASE_DIR / "data" / "processed" / "rankings_long.csv"
TRADE_VALUES_CSV = BASE_DIR / "data" / "processed" / "trade_values_long.csv"
RUN_STATUS_PATH = BASE_DIR / "data" / "last_run_status.json"
TRADE_STATUS_PATH = BASE_DIR / "data" / "last_trade_values_status.json"
PUSH_STATE_PATH = BASE_DIR / "data" / "supabase_push_state.json"

RANKINGS_INT_COLS = {"season", "week", "rank", "tier", "bye"}
RANKINGS_FLOAT_COLS = {"projection", "floor_proj", "ceiling_proj"}
TRADE_INT_COLS = {"season", "week", "rank"}
TRADE_FLOAT_COLS = {"value_col1", "value_col2"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _coerce_row(row: dict, int_cols: set[str], float_cols: set[str]) -> dict:
    out = dict(row)
    for col in int_cols:
        out[col] = int(out[col]) if out.get(col) not in (None, "") else None
    for col in float_cols:
        out[col] = float(out[col]) if out.get(col) not in (None, "") else None
    return out


def _read_state() -> dict:
    if PUSH_STATE_PATH.exists():
        return json.loads(PUSH_STATE_PATH.read_text(encoding="utf-8"))
    return {"rankings_rows_pushed": 0, "trade_values_rows_pushed": 0}


def _write_state(state: dict) -> None:
    PUSH_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _read_new_rows(csv_path: Path, already_pushed: int) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[already_pushed:]


def _insert(table: str, rows: list[dict], base_url: str, headers: dict) -> None:
    if not rows:
        return
    resp = requests.post(f"{base_url}/rest/v1/{table}", headers=headers, json=rows, timeout=30)
    resp.raise_for_status()


def _get_current_status(dataset: str, base_url: str, headers: dict) -> dict | None:
    resp = requests.get(
        f"{base_url}/rest/v1/in_season_pull_status",
        headers=headers, params={"dataset": f"eq.{dataset}", "select": "*"}, timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def _upsert_status(dataset: str, payload: dict, base_url: str, headers: dict) -> None:
    upsert_headers = dict(headers)
    upsert_headers["Prefer"] = "resolution=merge-duplicates"
    resp = requests.post(
        f"{base_url}/rest/v1/in_season_pull_status", headers=upsert_headers,
        json=[{"dataset": dataset, **payload}], timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    _load_env_file(BASE_DIR / ".env")
    base_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set -- skipping Supabase push.")
        return 1

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    state = _read_state()

    new_rankings = [
        _coerce_row(r, RANKINGS_INT_COLS, RANKINGS_FLOAT_COLS)
        for r in _read_new_rows(RANKINGS_CSV, state["rankings_rows_pushed"])
    ]
    try:
        _insert("in_season_rankings", new_rankings, base_url, headers)
        state["rankings_rows_pushed"] += len(new_rankings)
        print(f"Pushed {len(new_rankings)} new rankings row(s).")
    except requests.RequestException as e:
        print(f"WARNING: rankings push failed, will retry next run: {e}")

    new_trade_values = [
        _coerce_row(r, TRADE_INT_COLS, TRADE_FLOAT_COLS)
        for r in _read_new_rows(TRADE_VALUES_CSV, state["trade_values_rows_pushed"])
    ]
    try:
        _insert("in_season_trade_values", new_trade_values, base_url, headers)
        state["trade_values_rows_pushed"] += len(new_trade_values)
        print(f"Pushed {len(new_trade_values)} new trade-value row(s).")
    except requests.RequestException as e:
        print(f"WARNING: trade-value push failed, will retry next run: {e}")

    _write_state(state)

    for status_path, dataset_prefix, key_field in (
        (RUN_STATUS_PATH, "rankings", "combos"),
        (TRADE_STATUS_PATH, "trade_values", "positions"),
    ):
        if not status_path.exists():
            continue
        status = json.loads(status_path.read_text(encoding="utf-8"))
        for key, value in status.get(key_field, {}).items():
            dataset = f"{dataset_prefix}/{key}"
            ok = value == "ok"
            try:
                current = _get_current_status(dataset, base_url, headers)
                last_success_at = status["run_at"] if ok else (current or {}).get("last_success_at")
                _upsert_status(dataset, {
                    "last_attempt_at": status["run_at"],
                    "last_success_at": last_success_at,
                    "status": "healthy" if ok else "failed",
                    "message": None if ok else str(value),
                    "row_count": None,
                }, base_url, headers)
            except requests.RequestException as e:
                print(f"WARNING: status upsert failed for {dataset}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_push_to_supabase.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 6: Create `.env.example` and your real (gitignored) `.env`**

```
# in-season/.env.example
SUPABASE_URL=https://tdtchffawcmkvgrccjza.supabase.co
SUPABASE_SERVICE_ROLE_KEY=paste-the-service-role-key-here
```

Copy it to a real `.env` (already gitignored — `in-season/.gitignore` line 4) and paste in the actual service-role key (Supabase dashboard → Project Settings → API — the same key already in `Vampire/matchup-tool/.env`, since it's the same project).

- [ ] **Step 7: Manually verify against the real Supabase project**

```bash
python scripts/push_to_supabase.py
```

Expected: `Pushed N new rankings row(s).` / `Pushed N new trade-value row(s).` with no `WARNING:` lines. Then verify in Supabase:

```
execute_sql(project_id="tdtchffawcmkvgrccjza", query="select count(*) from in_season_rankings;")
```

Expected: count matches (or is less than, if this is before the Task 7 backfill) the current `rankings_long.csv` row count.

- [ ] **Step 8: Commit**

```bash
git add scripts/push_to_supabase.py scripts/__init__.py tests/test_push_to_supabase.py .env.example
git commit -m "Add push_to_supabase.py to sync local pulls into Supabase"
```

---

### Task 7: One-time backfill of existing history

**Files:**
- Create: `in-season/scripts/backfill_supabase.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python
"""One-time backfill: pushes the FULL existing rankings_long.csv /
trade_values_long.csv history to Supabase (ignoring push_to_supabase.py's
normal watermark), then sets data/supabase_push_state.json so the regular
push_to_supabase.py doesn't re-push what this just sent.

Run this ONCE: after Task 1 (schema exists), Task 5 (CSVs have
canonical_name), and Task 6 (push_to_supabase.py exists) are all done, and
BEFORE the first scheduled_pull.ps1 run that calls push_to_supabase.py.

Usage:
    python scripts/backfill_supabase.py
"""
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.push_to_supabase import (
    BASE_DIR,
    RANKINGS_CSV,
    RANKINGS_FLOAT_COLS,
    RANKINGS_INT_COLS,
    TRADE_FLOAT_COLS,
    TRADE_INT_COLS,
    TRADE_VALUES_CSV,
    _coerce_row,
    _insert,
    _load_env_file,
    _write_state,
)

CHUNK = 500


def _read_all_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    _load_env_file(BASE_DIR / ".env")
    base_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set -- aborting backfill.")
        return 1
    headers = {
        "apikey": service_key, "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    }

    rankings = [_coerce_row(r, RANKINGS_INT_COLS, RANKINGS_FLOAT_COLS) for r in _read_all_rows(RANKINGS_CSV)]
    trade_values = [_coerce_row(r, TRADE_INT_COLS, TRADE_FLOAT_COLS) for r in _read_all_rows(TRADE_VALUES_CSV)]

    print(f"Backfilling {len(rankings)} rankings row(s) and {len(trade_values)} trade-value row(s)...")

    for i in range(0, len(rankings), CHUNK):
        _insert("in_season_rankings", rankings[i:i + CHUNK], base_url, headers)
        print(f"  rankings {min(i + CHUNK, len(rankings))}/{len(rankings)}")
    for i in range(0, len(trade_values), CHUNK):
        _insert("in_season_trade_values", trade_values[i:i + CHUNK], base_url, headers)
        print(f"  trade values {min(i + CHUNK, len(trade_values))}/{len(trade_values)}")

    _write_state({
        "rankings_rows_pushed": len(rankings),
        "trade_values_rows_pushed": len(trade_values),
    })
    print("Backfill complete -- push state watermark updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
python scripts/backfill_supabase.py
```

Expected: prints progress in chunks of 500, ends with `Backfill complete -- push state watermark updated.`

- [ ] **Step 3: Verify row counts match**

```bash
python -c "import csv; print(sum(1 for _ in csv.DictReader(open('data/processed/rankings_long.csv', encoding='utf-8'))))"
```

Compare against:

```
execute_sql(project_id="tdtchffawcmkvgrccjza", query="select count(*) from in_season_rankings;")
```

Expected: the two counts match.

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_supabase.py data/supabase_push_state.json
git commit -m "Add one-time Supabase backfill script and run it"
```

---

### Task 8: Wire the push step into `scheduled_pull.ps1`

**Files:**
- Modify: `in-season/scripts/scheduled_pull.ps1`

- [ ] **Step 1: Add the push step right after the trade-values pull**

In `scripts/scheduled_pull.ps1`, immediately after this existing block (around line 167):

```powershell
    Log "Running pull_trade_values.py..."
    & $PythonExe "scripts\pull_trade_values.py" 2>&1 | ForEach-Object { Log $_ }
    $tradeValuesExit = $LASTEXITCODE
    Log "pull_trade_values.py exit code: $tradeValuesExit"
```

insert:

```powershell
    Log "Running push_to_supabase.py..."
    & $PythonExe "scripts\push_to_supabase.py" 2>&1 | ForEach-Object { Log $_ }
    Log "push_to_supabase.py exit code: $LASTEXITCODE"
```

Do **not** capture this into `$anyFailure` below — a Supabase push failure is not treated as a data-loss event (the local CSV already has the data), only as something to note. This matches the design's explicit call.

- [ ] **Step 2: Manually verify the full script still runs end-to-end**

```powershell
powershell -File scripts\scheduled_pull.ps1
```

Expected: log output shows `Running push_to_supabase.py...` after the trade-values pull, before the Vampire refresh section, and the script's final exit code still reflects only `$pullExit`/`$tradeValuesExit` (unchanged from before this task).

- [ ] **Step 3: Commit**

```bash
git add scripts/scheduled_pull.ps1
git commit -m "Wire push_to_supabase.py into the scheduled pull automation"
```

---

### Task 9: Prep the site scaffold

**Files:**
- Rename (git mv): `in-season/team-analyzer/` → `in-season/site/`
- Delete: `in-season/site/scrapers/` (old Playwright-based DraftSharks/Boone scraper — superseded by the `in-season` pipeline itself)
- Modify: `in-season/site/.env` (remove stale `DRAFTSHARKS_EMAIL`/`DRAFTSHARKS_PASSWORD` — this file is gitignored, so this is a local edit, not a git change)
- Delete: `in-season/site/vercel.json` (stale `version: 2`/`builds` config pointing at the bare `index.html`, not the Vite `dist/` build output — Vercel's zero-config Vite detection handles this correctly without it)

- [ ] **Step 1: Rename the folder**

```bash
cd "in-season"
git mv team-analyzer site
```

- [ ] **Step 2: Remove the stale scraper folder**

```bash
git rm -r site/scrapers
```

- [ ] **Step 3: Remove the stale Vercel config**

```bash
git rm site/vercel.json
```

- [ ] **Step 4: Clean the local `.env`**

Open `site/.env` and delete the `DRAFTSHARKS_EMAIL=`/`DRAFTSHARKS_PASSWORD=` lines (leave the file empty or delete it entirely — nothing in `site/src` currently reads these). This file is gitignored, so no git command is needed for this step; **note there is a real plaintext password in this file today — worth rotating that DraftSharks account password since it's been sitting in a local file, independent of anything git-related.**

- [ ] **Step 5: Verify the app still builds after the rename/removal**

```bash
cd site
npm install
npm run build
```

Expected: `tsc -b && vite build` completes without errors, producing a `dist/` folder. (The stub pages/components are all self-contained TS/TSX with no imports from `scrapers/`, so removing that folder should not affect the build — if `npm run build` does fail on a missing import, find and fix that import as part of this step, not as a follow-up.)

- [ ] **Step 6: Commit**

```bash
cd ..
git add site
git commit -m "Rename team-analyzer scaffold to site, strip stale scraper/config"
```

---

### Task 10: GitHub + Vercel (manual — Jared runs this, not a subagent)

This task needs your own GitHub and Vercel accounts — hand this off rather than having an agent attempt it.

**Push the repo to GitHub:**

```bash
cd "C:\Users\jmfra\OneDrive\Documents\Fantasy Football\in-season"
git remote add origin https://github.com/<your-github-username>/in-season.git
git branch -M main
git push -u origin main
```

(Create the empty `in-season` repo on GitHub first if it doesn't exist yet — github.com/new, no README/gitignore/license, so the push above doesn't conflict.)

**Connect Vercel:** in the Vercel dashboard, **Add New → Project → Import** the `in-season` GitHub repo, then set **Root Directory** to `site` before deploying (Vercel auto-detects the Vite framework preset once the root directory is correct — no `vercel.json` needed). No environment variables are required for this first deploy since no page queries Supabase yet; add `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` in the Vercel project's Settings → Environment Variables once the first page that needs them is built.

---

## Self-Review Notes

- **Spec coverage:** Supabase schema (Task 1) ✓, push automation (Task 6, 8) ✓, player identity (Task 2, 4) ✓, scaffold prep (Task 9) ✓, GitHub+Vercel hosting (Task 10) ✓. Backfill (Task 7) and the CSV migration (Task 5) were spec-mentioned "one-time" items, both covered. Out-of-scope items from the spec (players registry table, shared calculations, UI components) are correctly not tasked here.
- **Placeholder scan:** none found — every step has concrete code/commands.
- **Type consistency:** `canonical_name_for(raw_name, aliases=None)` signature is used identically in Task 2's tests, Task 4's `normalize.py`, and Task 5's migration script. `_coerce_row`, `_read_new_rows`, `_read_state`, `_write_state` signatures in Task 6 match their use in Task 7's backfill script exactly (imported, not reimplemented).
- **Correction applied during review:** the original spec's "log unmatched names" idea is dropped per the header's "Deviation from spec" note — implementing it as literally specified would have logged nearly every ordinary player name every run, which is noise, not signal.
