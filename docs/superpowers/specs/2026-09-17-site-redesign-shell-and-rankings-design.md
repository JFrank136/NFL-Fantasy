# Site redesign: visual shell + real Rankings/Trade Values pages

## Goal

Replace `in-season/site`'s leftover pre-Supabase ChatGPT scaffold (dark
"Team Analyzer" theme, flat tab bar, CSV-upload pages that silently render
blank) with a real visual design, a navigation shell that scales to the
full `SITE_ROADMAP.md` page list, and the first real content on the two
pages that already have live Supabase data: Rankings and Trade Values.

This is Phase 1 of the larger site overhaul. The rest of `SITE_ROADMAP.md`'s
V1 pages (Home, Start/Sit, Player Comparison, Add/Drop, Trade Analyzer,
Movers & Fallers, Expert Disagreement, Team Analyzer, Data Health) are
explicitly out of scope here and will get their own spec(s) later.

## Non-goals

- Building any of the 9 roadmap V1 pages beyond Rankings/Trade Values.
- Player detail pages, saved views, or tiers (roadmap marks these "later").
- Roster-aware anything (V2).
- Changing the underlying pipeline/scrapers (that work is already done and
  live as of 2026-09-17 — DraftSharks ROS rankings, plus CBS/FantasyPros/
  RSJ/USA Today trade values, all pushed to Supabase).

## 1. Visual Design System

**Direction:** "Turf Bright" — a football-themed dark palette, chosen over
a near-black "Command Center" option and a light "Clean Studio" option
during visual brainstorming. Jared's explicit feedback: liked the football
feel of the turf-green direction, disliked the near-black variant ("dull
and dark") and the light variant ("not great on the eyes").

**Palette (hex values from the approved mockup):**

| Token | Value | Use |
|---|---|---|
| `--bg-page` | `#1f4a3a` | Main content background |
| `--bg-sidebar` | `#193c2f` | Sidebar background |
| `--bg-card` | `#254f3e` | Cards, inputs, table body |
| `--bg-card-border` | `#366b54` | Card/input borders |
| `--bg-table-header` | `#1f4a3a` / border `#2b5744` | Table header row |
| `--text-primary` | `#fbf8ef` | Primary text (cream) |
| `--text-secondary` | `#a9c9b8` | Secondary/muted text |
| `--accent-gold` | `#e8b23d` | Active nav item, primary rank (#1), active filter |
| `--accent-gold-text` | `#241a03` | Text on gold background |
| `--signal-up` | `#8fe0a8` | Positive movement |
| `--signal-down` | `#ec9186` | Negative movement |

**Typography:** system-ui sans-serif stack (matches current Tailwind
config, no new font load needed). Nav/section labels: bold, uppercase,
letter-spacing. Table numeric columns: right-aligned, tabular figures.

**Implementation:** replace the `.card`/`.btn`/`.input`/`.table`/`.tab`
etc. utility classes in `src/index.css` with the new palette. Keep the same
class names where the shape of the component is unchanged (e.g. `.card`,
`.input`) so the diff stays focused on color/spacing, not a rewrite of
every component's markup.

## 2. Branding

Header text changes from "Team Analyzer" / "DS-anchored, lineup-aware
trade value toolkit" to "🐱 Shambert's Lab". Subtitle can be dropped or
replaced with something short (e.g. "Weekly rankings & trade values") —
implementer's call, not load-bearing.

## 3. Navigation Shell

- **Desktop (≥768px):** left sidebar, fixed width (~150-180px), containing
  the brand name/logo at top and a vertical list of page links. Active
  page highlighted with the gold accent background.
- **Mobile (<768px):** sidebar collapses behind a hamburger icon in a top
  header bar; tapping it slides out an off-canvas drawer (dark overlay
  behind it) with the same link list. Standard responsive drawer pattern,
  no animation library needed — CSS transform/transition is sufficient.
- Nav currently lists **Rankings** and **Trade Values** only. Structure the
  component (a `NAV_ITEMS` array feeding both the sidebar and drawer) so
  adding a new roadmap page later is a one-line change, not a rewrite.

## 4. Legacy Cleanup

Delete entirely (dead CSV-upload scaffold, no live path forward):

- `src/pages/Players.tsx`, `Trends.tsx`, `Roster.tsx`, `Trade.tsx`,
  `Weeks.tsx`, `Settings.tsx`
- `src/components/PlayersTable.tsx`, `TrendsView.tsx`, `RosterAnalyzer.tsx`,
  `TradeSandbox.tsx`, `WeekManager.tsx`, `BlendEngine.tsx`,
  `components/Settings.tsx`
- `src/state/store.ts` (Zustand CSV-upload store)
- `src/lib/csv.ts`, `src/lib/vorp.ts` (only used by the deleted pages)
- Update `src/pages/index.ts` barrel and `App.tsx` to drop all references.
- Keep `src/lib/regression.ts` (`robustLinearFit`/`applyScale`) and
  `src/lib/names.ts` (`tidyName`/`canonicalKey`) — both get reused by the
  new Rankings page's blended-value calculation (see below).

## 5. Rankings Page

Two tabs, **ROS** (default) and **Weekly**. Both read live from Supabase —
no CSV upload anywhere in this page.

### Shared controls (both tabs)

- Player search (text input, matches `player_name` substring)
- Position filter (ALL / QB / RB / WR / TE)
- Scoring toggle (Half-PPR / PPR) — maps to `scoring` column values
  `half-ppr` / `ppr`
- Sortable columns (click header to sort, toggle asc/desc)
- Freshness timestamp (max `pulled_at` in the current result set), matching
  the pattern already built for the current Rankings/Trade Values pages

V1 is table-only: no player detail page, no tiers, no saved views (roadmap
marks these "later" — don't build ahead of the spec).

### ROS tab

Data source: `in_season_ros_rankings` (Draft Sharks) joined against
`in_season_trade_values` where `source = 'boone'` (Boone's ROS trade
value), matched on `canonical_name`.

Columns:

| Column | Source |
|---|---|
| Overall rank | Recomputed client-side after blending (see below), not a stored column |
| Player | `player_name` |
| Position | `position` |
| Team | `team` |
| Blended ROS value | Computed (see below) |
| Draft Sharks ROS value | `in_season_ros_rankings.ds_value` |
| Boone ROS value | `in_season_trade_values.value_col1` or `value_col2` per scoring format for RB/WR/TE (HALF/PPR labels). For QB rows, always use the `1QB` column regardless of the page's Half-PPR/PPR toggle — confirmed with Jared that 1QB is the correct equivalent for both scoring formats at the QB position, so the toggle has no effect there by design, not by omission. |
| Draft Sharks ceiling/upside | `in_season_ros_rankings.ceiling_proj` |
| ROS change | Blended ROS value now minus blended ROS value as of the previous distinct `pulled_at` for that player (see below) |

**Blended ROS value calculation:** reuse `robustLinearFit`/`applyScale`
from `src/lib/regression.ts` (already written for the old weekly
BlendEngine, same technique applies here):

1. For the selected scoring format, build two maps keyed by
   `canonicalKey(tidyName(name), pos, team)` (from `src/lib/names.ts`):
   Draft Sharks' `ds_value` and Boone's matched value column.
2. Fit a linear scale (`robustLinearFit`) from Boone's value onto Draft
   Sharks' value using players present in both maps.
3. Apply that scale to every Boone value (`applyScale`), then blend
   50/50 with Draft Sharks' value (unweighted average of the two,
   post-scaling) for players present in both; use the single available
   value (no blend) for players present in only one source.
4. Re-rank the blended result across **all positions together** (confirmed
   with Jared: "Overall rank" is a single cross-position ordering, not
   per-position). The existing position filter still applies on top of
   this — filtering to RB just hides non-RB rows, it does not renumber the
   remaining rows 1..N; the displayed rank stays the player's overall rank.

**ROS change:** query the previous distinct `pulled_at` timestamp (per
player, per source, per scoring) from the same tables (not just the
`_latest` views, which only carry the newest snapshot), run the same blend
calculation against that older snapshot, and show
`current_blended - previous_blended`. If no prior snapshot exists yet
(first week of data), show an em dash or "New" rather than 0 or blank.

### Weekly tab

Data source: `in_season_rankings_latest`, filtered to the current week
(same week-detection logic already built in the existing Rankings page —
default to the max week Boone/Smythe have data for, since Draft Sharks
publishes all 18 weeks at once and isn't a reliable "current week"
signal).

Columns:

| Column | Source |
|---|---|
| Aggregate weekly rank | Computed (see below) |
| Player | `player_name` |
| Position | `position` |
| Team | `team` |
| Draft Sharks rank | `rank` where `source = 'draftsharks'` |
| Boone rank | `rank` where `source = 'boone'` |
| DS projection | `projection` where `source = 'draftsharks'` |
| Floor | `floor_proj` where `source = 'draftsharks'` |
| Ceiling | `ceiling_proj` where `source = 'draftsharks'` |
| Opponent | `opponent` (from any source that has it for that player) |

No "Matchup rating" column — that data doesn't exist yet (only opponent
name). Add it later if/when a matchup-rating source is pulled.

**Aggregate weekly rank calculation:** weighted average of each source's
*position rank* (not raw value — DS/Boone/Smythe don't share a value
scale for weekly data the way ROS does), using the same weights already
tuned in `Draft/config/settings.yaml`'s `consensus.weights`:

```
default: { boone: 0.30, draftsharks: 0.50, smyth: 0.20 }
QB:      { boone: 0.40, draftsharks: 0.40, smyth: 0.20 }
```

For a player missing from one source, redistribute that source's weight
proportionally across the sources that do have them (don't just drop the
weight and leave the total under 1.0). Re-rank the weighted-average result
within position to produce the displayed "Aggregate weekly rank".

## 6. Trade Values Page

Same restyle as Rankings (sidebar shell, Turf Bright palette). Content
changes from last session's version: source filter now includes all 5
live sources (Boone, CBS, FantasyPros, RSJ, USA Today), not just Boone.
Columns stay as currently built (rank, player, team, position, source,
value_col1/2 with their labels) — no new columns needed here, this page
just needs the restyle + the additional source options in the existing
filter dropdown.

## Risks for the implementation plan to be aware of

- `in_season_ros_rankings` only has one week of history as of this spec
  (first-ever pull, 2026-09-17) — "ROS change" will show "New" for every
  player until a second weekly pull happens. Not a bug, just worth noting
  so it isn't mistaken for one during testing.
