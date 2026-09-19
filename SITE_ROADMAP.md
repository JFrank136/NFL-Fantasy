# In-Season Fantasy Site Roadmap

## Goal

Build a single in-season fantasy football site that turns the existing weekly/ROS data pipeline into practical decision tools.

Claude should use this file as the implementation checklist and source of truth for the site. Check items off as they are completed. Do not invent major features or change product logic without updating this roadmap first.

The site should stay simple in V1: generic tools that save time comparing Draft Sharks, Justin Boone, and derived values. V2 adds logins, team imports, roster-aware recommendations, and playoff-specific logic.

---

# 1. Shared Foundation

These should be built before most page-specific work to avoid duplicating logic.

## Supabase / Data Layer

- [ ] Design and implement Supabase storage for validated in-season data
- [ ] Preserve historical pulls rather than overwriting prior snapshots
- [ ] Store weekly rankings/projections
- [ ] Store ROS / trade values
- [ ] Store DS ceiling / upside values
- [ ] Store source timestamps / freshness
- [ ] Keep raw source values available for transparency
- [ ] Define queries/helpers for current/latest values and historical changes

## Shared Player Identity

- [ ] Create one canonical player identity system
- [ ] Reuse the existing aliases/name-matching source rather than creating new copies
- [ ] Match Boone / Draft Sharks / Smythe rows to the same player record
- [ ] Centralize aliases and player normalization
- [ ] Avoid page-specific name-matching logic

## Shared Calculations

- [ ] Aggregate weekly rank using Draft Sharks + Boone + Smythe
- [ ] Build blended ROS value using Draft Sharks + Boone
- [ ] Start ROS weighting at 50% Draft Sharks / 50% Boone
- [ ] Normalize source value scales before blending
- [ ] Preserve meaningful gaps between players rather than relying only on rank
- [ ] Calculate ROS value movement over time
- [ ] Calculate source-specific movement over time
- [ ] Calculate Boone vs Draft Sharks disagreement
- [ ] Calculate source-direction disagreement
- [ ] Add reusable confidence logic based on value/rank gaps
- [ ] Keep weights/thresholds configurable because they will be retested after a full season

## Reusable UI Components

- [ ] Shared player search/select component
- [ ] Shared side-by-side comparison table
- [ ] Support best/worst highlighting by row
- [ ] Shared player value display
- [ ] Shared source transparency display
- [ ] Shared confidence indicator
- [ ] Shared position filters
- [ ] Shared timeframe filters
- [ ] Shared stale-data warning banner

## Global Context

- [ ] Current NFL week
- [ ] Scoring setting
- [ ] Data freshness state
- [ ] Current/latest dataset selection

---

# 2. Home Dashboard — V1

## Purpose

Quickly show whether the data is healthy and what changed in ROS value.

## Must Have

- [ ] Data health summary
- [ ] Last successful update
- [ ] Compact source status
- [ ] Top 5 ROS risers
- [ ] Top 5 ROS fallers
- [ ] Show current blended ROS value and change
- [ ] Link to full Movers & Fallers page

## V1 Notes

- ROS-focused
- No personalized roster content yet
- Keep the homepage lightweight
- Normal site navigation handles Start/Sit, Trade, Add/Drop, etc.

## V2

- [ ] Personalized dashboard after logins/team imports
- [ ] Surface roster weaknesses
- [ ] Surface players on user teams with major value changes
- [ ] Surface waiver opportunities
- [ ] Surface start/sit decisions
- [ ] Surface trade needs

---

# 3. Start / Sit

## Purpose

Make current-week lineup decisions easy by comparing 2–5 players side by side.

Typical use will be 2–3 players, including FLEX decisions.

## Comparison Fields

- [ ] Aggregate weekly rank — primary decision anchor
- [ ] Draft Sharks weekly rank
- [ ] Boone weekly rank
- [ ] Draft Sharks weekly projection
- [ ] Draft Sharks floor
- [ ] Draft Sharks ceiling
- [ ] Matchup rating
- [ ] ROS value/rank as secondary context
- [ ] Confidence level

## Behavior

- [ ] Support 2–5 players
- [ ] Allow FLEX comparisons across RB/WR/TE
- [ ] Use row-based comparison so values can be scanned left-to-right
- [ ] Highlight best/worst values by row
- [ ] Show recommended starter
- [ ] Show confidence: High / Medium / Toss-up
- [ ] Add 1–2 short reasons based on biggest differences

## Recommendation Logic

- [ ] Aggregate weekly rank is the anchor
- [ ] Boone and Draft Sharks shown separately for transparency
- [ ] Projection/floor/ceiling/matchup are supporting context
- [ ] ROS context is secondary and should mainly help with "start your studs" situations
- [ ] Develop weighting model later
- [ ] Backtest weighting against historical weekly outcomes
- [ ] Tune weights after enough data exists

## Not Needed in V1

- Injury/news feed
- ROS-heavy recommendation logic
- Team-import-specific automation

---

# 4. Player Comparison

## Purpose

Neutral ROS comparison when the user wants to compare players without entering a trade or waiver workflow.

## Must Have

- [ ] Compare 2–5 players
- [ ] Side-by-side table
- [ ] Blended ROS value
- [ ] Draft Sharks ROS value
- [ ] Boone ROS value
- [ ] Draft Sharks upside / ceiling value
- [ ] ROS rank
- [ ] Position rank
- [ ] ROS trend / recent movement
- [ ] SOS
- [ ] Expert/value disagreement
- [ ] Highlight best/worst values by row
- [ ] Optional short summary of biggest differences

## Notes

- ROS-focused
- Start/Sit handles weekly comparisons
- No forced trade recommendation
- No forced add/drop recommendation
- Reuse the same shared comparison components used by Trade and Add/Drop

---

# 5. Add / Drop

## Purpose

Handle waiver decisions as a two-step problem:

1. Is anyone worth adding?
2. If yes, who should be dropped?

This should also work as a broader comparison tool because multiple waiver players may be better than multiple bench players.

## Must Have

- [ ] Compare multiple add candidates
- [ ] Compare multiple current roster/bench candidates
- [ ] Allow user to compare several waiver players against several bench players
- [ ] Blended ROS value
- [ ] Draft Sharks upside / ceiling value
- [ ] ROS trend
- [ ] Current-week outlook as secondary context
- [ ] SOS shown as context
- [ ] Position shown clearly

## Evaluation Philosophy

- ROS value answers: "Who is the better player right now?"
- Upside value answers: "Who has the better best-case outcome?"
- Do not force ROS and upside into one rigid score in V1
- A lower-current-value player may still be worth rostering for upside
- Do not add special cross-position logic in V1

## V2

- [ ] Team imports automatically identify weakest bench players
- [ ] Cross-position roster impact
- [ ] Roster strength determines whether to favor current ROS vs upside
- [ ] League availability / waiver discovery
- [ ] Automatically surface multiple worthwhile adds

## Waiver Wire

Do not build Waiver Wire as a separate V1 page.

Waiver Wire should later become a discovery layer inside Add/Drop:
- [ ] Filter to players actually available in the user's league
- [ ] Rank available players by ROS
- [ ] Rank available players by upside
- [ ] Show biggest risers
- [ ] Send selected players directly into Add/Drop comparison

---

# 6. Trade Analyzer

## Purpose

Determine which side of a trade is better based primarily on blended ROS value.

V1 is generic/manual. Roster impact comes later with team imports.

## Trade Setup

- [x] Support 1–4 players per side
- [x] Player-only trades
- [x] Manual player selection in V1
- [x] Uneven trades allowed: 2-for-1, 3-for-2, etc.
- [x] Show both sides side-by-side

## Value Foundation

Sources:
- Draft Sharks ROS value
- Justin Boone trade/ROS value

Logic:
- [x] Normalize both sources onto a common scale
- [x] Preserve magnitude differences between players
- [x] Blend 50% Draft Sharks / 50% Boone initially
- [ ] Keep weights configurable
- [x] Do not use average rank as the main trade metric

## Player-Level Display

- [x] Blended ROS value
- [x] Draft Sharks ROS value
- [x] Boone ROS value
- [x] Position
- [ ] ROS rank
- [ ] Position rank if available

## Side-Level Display

- [x] Total blended value
- [ ] Difference vs other side
- [x] Percentage difference
- [x] Best player in the trade
- [ ] Number of players on each side
- [x] Preferred side
- [x] Confidence: Close / Medium / High
- [x] 1–2 sentence explanation

## Best-Player / Consolidation Logic

V1:
- [x] Show raw total value clearly
- [x] Clearly identify the strongest individual player
- [x] Do not force an aggressive best-player premium yet
- [x] Let the user judge whether consolidation is worth it

Later:
- [ ] Develop a consolidation / trade-tax adjustment
- [ ] Account for how elite the best player is
- [ ] Account for value above replacement
- [ ] Account for whether incoming depth would actually matter
- [ ] Tune with real trade examples and roster context

## Confidence

- [x] Base primarily on % difference in total blended ROS value
- [x] Always show underlying values
- [x] Keep thresholds configurable
- [x] Avoid false precision

## V2 — Roster-Aware Trade Analysis

- [ ] Starting lineup strength before vs after
- [ ] Positional strength changes
- [ ] Depth gained/lost
- [ ] Whether incoming players actually become starters
- [ ] Consolidation / trade tax logic
- [ ] More detailed DS-style trade analysis

---

# 7. Movers & Fallers

## Purpose

Show which players are gaining or losing value.

## Controls

Metric selector:
- [ ] Blended ROS value
- [ ] Boone ROS value
- [ ] Draft Sharks ROS value
- [ ] Draft Sharks ceiling / upside
- [ ] ROS rank later if useful

Timeframe selector:
- [ ] Latest change
- [ ] Since last week
- [ ] Additional ranges later

## Results

- [ ] Top risers
- [ ] Top fallers
- [ ] Current value
- [ ] Previous value
- [ ] Change
- [ ] Current rank
- [ ] Position
- [ ] Link/click into player detail later

## Notes

Prioritize value movement over rank movement when possible. A small rank change can represent a large or tiny real value change.

---

# 8. Expert Disagreement

## Purpose

Show where Boone and Draft Sharks disagree, either in current value or direction of movement.

## Views

### Biggest Current Disagreements

- [ ] Boone ROS value/rank
- [ ] Draft Sharks ROS value/rank
- [ ] Difference/gap
- [ ] Sort by largest disagreement

### Direction Disagreements

- [ ] Boone recent change
- [ ] Draft Sharks recent change
- [ ] Flag cases where one rises while the other falls or stays flat
- [ ] Show size of movement

## Filters

- [ ] Position
- [ ] Timeframe

## Notes

Do not add a separate "agreement movers" section in V1. Those are already reflected in Movers & Fallers.

---

# 9. Team Analyzer — Rebuild Existing Tool

## Purpose

Update the existing Team Analyzer rather than build a separate "Roster Analyzer."

Main use cases:
- Quickly see strengths/weaknesses across multiple fantasy teams
- Identify positions to upgrade
- Identify positions with enough strength/depth to trade from
- Compare overall team quality across leagues

## Migration / Cleanup

- [ ] Remove dependence on the old separate scrapers
- [ ] Feed the tool from the new in-season pipeline / Supabase
- [ ] Use blended ROS values
- [ ] Reuse shared player identity and comparison logic

## Position-Level Analysis

For each position:
- [ ] Starter strength
- [ ] Usable depth
- [ ] Upside depth
- [ ] FLEX support where relevant
- [ ] Overall position score
- [ ] Upgrade priority
- [ ] Short summary

## Starter Strength

- [ ] Anchor mainly on blended ROS value
- [ ] Evaluate positions relative to that position
- [ ] RB/WR should account for FLEX competition
- [ ] Compare next 2–3 FLEX options
- [ ] Note large drop-offs between starters
- [ ] QB/TE logic should recognize that one elite starter can reduce the value of depth

## Depth Logic

Separate:
- Usable depth — players with enough ROS value to realistically enter the lineup
- Upside depth — players who may be low-value now but have meaningful ceiling

Rules:
- [ ] Full bench can be considered
- [ ] Low-value depth becomes less important after a threshold
- [ ] Upside matters more for lower-end bench spots
- [ ] Handcuffs can count as either usable depth or upside depending on standalone value
- [ ] RB/WR depth generally matters more than QB/TE depth
- [ ] Depth importance depends on starter quality

## Team-Level Analysis

- [ ] Overall starter strength
- [ ] Overall depth
- [ ] Overall upside
- [ ] Overall team score / index
- [ ] Top upgrade priorities
- [ ] Position strengths/weaknesses
- [ ] Compare multiple teams/leagues

## Seasonal Weighting

Early/midseason:
- Starter strength matters
- Depth matters for injuries/byes

Later season:
- Starting lineup strength matters more

Later:
- [ ] Shift weighting based on playoff probability
- [ ] Reduce emphasis on ordinary depth when playoff position is secure

## V2

- [ ] Compare position strength against league opponents
- [ ] League-relative team grades
- [ ] Automatic team imports
- [ ] Personalized trade targets
- [ ] Personalized waiver needs

---

# 10. Data Health

## Purpose

Make it obvious whether the site's data is current and trustworthy.

## Overall Status

- [ ] Healthy
- [ ] Warning
- [ ] Failed

## Show by Dataset / Source

Weekly rankings:
- [ ] Draft Sharks
- [ ] Boone
- [ ] Smythe

ROS / trade values:
- [ ] Draft Sharks ROS
- [ ] Boone trade values

For each:
- [ ] Last successful pull
- [ ] Age of current data
- [ ] Validation status
- [ ] Failure/warning message
- [ ] Stale-data warning

## Behavior

- [ ] Site continues operating if one source fails
- [ ] Existing data remains available
- [ ] Clearly warn when tools are using incomplete/stale data
- [ ] Use dataset-specific stale thresholds where needed
- [ ] Keep row counts/debug-level details out of the main UI unless useful later

## Home Integration

- [ ] Compact status summary
- [ ] Link to full Data Health page

Existing failure emails remain useful; this page is for knowing what data the site is currently using.

---

# 11. V1 Navigation

- [ ] Home
- [ ] Start / Sit
- [ ] Player Comparison
- [ ] Add / Drop
- [ ] Trade Analyzer
- [ ] Movers & Fallers
- [ ] Expert Disagreement
- [ ] Team Analyzer
- [ ] Data Health

Do not create separate V1 pages for:
- Waiver Wire
- Rankings Updates
- Playoffs

Those are either covered elsewhere or belong in later versions.

---

# 12. Suggested Implementation Order

The order should reduce duplicated work and build shared systems before page-specific logic.

1. [ ] Supabase + historical data model
2. [ ] Shared player identity / aliases
3. [ ] Shared calculations and data-access layer
4. [ ] Reusable player selector
5. [ ] Reusable comparison table
6. [ ] Data freshness/status layer
7. [ ] Data Health page
8. [ ] Movers & Fallers
9. [ ] Expert Disagreement
10. [ ] Player Comparison
11. [ ] Start / Sit
12. [ ] Add / Drop
13. [ ] Trade Analyzer
14. [ ] Team Analyzer rebuild
15. [ ] Home dashboard
16. [ ] V2 logins/team imports
17. [ ] V2 roster-aware tools
18. [ ] Playoff tools

---

# 13. V2 / Later

## Accounts / Team Imports

- [ ] User login
- [ ] League import
- [ ] Team import
- [ ] League settings import
- [ ] Roster-aware comparisons
- [ ] Personalized dashboard

## Waiver Discovery

- [ ] League-specific available players
- [ ] Best available by ROS
- [ ] Best available by upside
- [ ] Personalized weakest bench spots

## Trade Intelligence

- [ ] Roster-aware impact
- [ ] Starter changes
- [ ] Depth changes
- [ ] League-relative positional needs
- [ ] Trade finder later if worthwhile

## Playoffs

- [ ] Playoff SOS
- [ ] Weeks 14–17 planning
- [ ] Playoff lineup strength
- [ ] Stash targets
- [ ] Depth vs starter weighting shift
- [ ] Playoff probability integration

---

# 14. Testing / Calibration

These tools should stay transparent and tunable rather than pretending the initial weights are final.

## After Enough 2026 Data Exists

- [ ] Evaluate Draft Sharks vs Boone ROS accuracy
- [ ] Revisit 50/50 ROS blend
- [ ] Evaluate weekly ranking aggregate accuracy
- [ ] Backtest Start/Sit recommendation logic
- [ ] Tune confidence thresholds
- [ ] Evaluate normalization method
- [ ] Develop/test consolidation premium for trades
- [ ] Tune usable-depth thresholds
- [ ] Tune starter vs depth weighting
- [ ] Tune late-season/playoff weighting

---

# Product Principles

- Keep V1 generic and fast.
- Show source values for transparency.
- Do not hide uncertainty behind one score.
- Reuse shared comparison logic instead of rebuilding it page by page.
- Preserve historical data because movement over time is a core feature.
- Do not duplicate scraping or name-matching logic that already exists.
- Prefer useful summaries over overloaded dashboards.
- Team imports unlock the smarter V2 logic; do not force roster-aware behavior before the data exists.
- Keep formulas and thresholds configurable so they can be tested and improved after a full season.
