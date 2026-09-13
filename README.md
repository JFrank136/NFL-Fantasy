# In-Season Tools

Weekly fantasy football data pipeline (Draft Sharks, Justin Boone, and — pending
a confirmed weekly source — Joel Smyth) feeding a set of in-season tools:
start/sit, trade, waiver wire, rest-of-season, and whatever else comes later.

## Why this exists separately from `Draft/`

`Draft/` builds the one-time preseason draft board. This project pulls **weekly**
rankings/projections throughout the season and keeps every week's pull instead of
overwriting it, since a week's rankings get updated multiple times before kickoff
and Jared wants the history preserved, not just the latest snapshot.

## Sources (see `docs/DATA.md` for verified request/response shapes)

- **Draft Sharks weekly rankings** — public, unauthenticated `load-rows` endpoint.
  No login needed (unlike `Draft/`'s draft-day CSV export, which does require one).
- **Justin Boone (via Yahoo)** — Yahoo's article embeds a FantasyPros partner
  widget; pulled directly from FantasyPros' own public JSON endpoint instead of
  scraping Yahoo's bot-protected HTML.
- **Joel Smyth** — same FantasyPros mechanism is assumed (`id=7604`, the same ID
  `Draft/src/sources/yahoo_consensus.py` already resolved by name for the
  draft-day board), but this is **unconfirmed for weekly rankings** — his Week 1
  numbers aren't published yet as of this writing (his page says PPR rankings
  come Thursday). `validate.py` flags a Smyth pull that looks identical to
  Boone's, since an invalid/unpublished expert ID has been observed to silently
  fall back to a default rather than erroring.
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

## Storage (for now)

Local files only — `data/raw/` (immutable timestamped snapshots) and
`data/processed/rankings_long.csv` (append-only, standardized long format).
Supabase comes later, once the schema has proven itself against a few real
weeks of data; see `docs/DATA.md` for the planned table shape.

## Name matching

Deliberately **not duplicated here**. `Draft/data/aliases.csv` is the single
source of truth (same file Vampire's `name-matching.js` already reads from) —
read it directly rather than forking a third copy. The Draft Sharks → Vampire
weekly-projection handoff (see `../Vampire/matchup-tool/scripts/refresh-weekly-projection.js`)
reuses Vampire's own `normalizeName` instead of re-implementing matching here.

## Usage

```bash
pip install -r requirements.txt
python scripts/pull_week.py --week 1 --source draftsharks --scoring half-ppr,ppr
python scripts/pull_trade_values.py --week 1
```

See `scripts/pull_week.py --help` for all options. Every run prints a summary
(rows pulled, validation warnings/failures, output paths) and exits non-zero on
a validation failure — treat that as "this week needs attention," not a soft
warning to skim past.
