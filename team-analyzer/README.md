# Team Analyzer (Vercel-ready)

DS-anchored, lineup-aware **trade value** analyzer for fantasy football.

## Highlights
- Upload **Boone** and **DraftSharks** CSVs (drag a folder). Week is auto-detected from filename.
- **Scale-match** Boone to DS via robust linear regression (per week), then blend (**DS 60 / Boone 40** by default).
- Switch table mode: **Blended**, **DS (raw)**, **Boone (raw)**.
- **Trends** (Δ vs previous week) with Top Risers/Fallers.
- **Roster Analyzer** and **Trade Sandbox (beta)** with bench discount & season stage.
- Saved leagues/teams are local-first (localStorage). No network calls.

## Quick start
```bash
pnpm i
pnpm dev
# or
npm i
npm run dev
```

## Build & deploy
```bash
pnpm build
# Deploy on Vercel as a static app
```

## CSV conventions
- Boone: `PosRank, Name, Unnamed: 2, 0.5ppr, 1ppr`
- DraftSharks: `Name, Pos, 0.5ppr_value, 1ppr_value`
- File names: include `weekN` and `boone` or `draftsharks` (case-insensitive).

## Notes
- K/DST excluded by default.
- League import is via Settings (paste league settings text). PPR auto-detected; lineup template editable.
- This is v1 core. Future: Needs Matrix, playoff tilt, source plugins, richer fuzzy review, visuals.
