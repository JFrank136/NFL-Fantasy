# Team Analyzer — File Guide

## Top level

- **`package.json`** — declares this as a Vite + React + TypeScript app. Notable dependencies: `zustand` (state management), `papaparse` (CSV parsing), `@tanstack/react-table` (the data tables), `recharts` (trend charts), `immer` (for writing state updates as if they were mutable).
- **`README.md`** — the original short pitch and quick-start instructions; still accurate for how to run the app.
- **`index.html`**, **`vite.config.ts`**, **`tsconfig.json`**, **`tailwind.config.ts`**, **`postcss.config.js`** — standard front-end tooling config, nothing fantasy-football-specific.
- **`vercel.json`** — deployment config for hosting this as a static site on Vercel.

## `src/` — the web app

- **`App.tsx`** — the app shell. Renders a header, the blend-settings panel, and a tab bar switching between six views: Players, Trends, Roster, Trade, Weeks, Settings.
- **`main.tsx`** — standard React entry point, mounts `App`.
- **`index.css`** — global styles (Tailwind-based).

### `src/components/`
- **`Header.tsx`** — top banner/branding.
- **`BlendEngine.tsx`** — the UI controls for adjusting the DraftSharks/Boone blend weight and which sources are active; this is the panel that drives the core blending logic.
- **`PlayersTable.tsx`** — the sortable/filterable table of all players and their values, used by the Players tab.
- **`TrendsView.tsx`** — week-over-week change view, showing top risers and fallers.
- **`RosterAnalyzer.tsx`** — evaluates a saved roster against the blended values (e.g., total roster value, weak spots).
- **`TradeSandbox.tsx`** — lets Jared compare what's being given up vs. received in a hypothetical trade, using blended values. Marked "beta" in the README.
- **`WeekManager.tsx`** — UI for uploading/managing which weeks of data have been loaded.
- **`Settings.tsx`** — league configuration UI (roster slots, PPR type, team count) and CSV/league-text import.

### `src/pages/`
Thin wrapper components (`Players.tsx`, `Trends.tsx`, `Roster.tsx`, `Trade.tsx`, `Weeks.tsx`, `Settings.tsx`) that each render the corresponding component above for its tab; `index.ts` is the barrel file that re-exports them for `App.tsx`.

### `src/lib/` — the actual logic, decoupled from UI
- **`csv.ts`** — CSV parsing helpers built on `papaparse`.
- **`sources.ts`** — maps raw CSV rows from each source (Boone, DraftSharks) into a common internal shape, handling the fact that column names have changed between old and new export formats from each source.
- **`names.ts`** — name normalization ("tidying") so the same player from two different sources with slightly different name formatting matches up.
- **`regression.ts`** — the robust linear regression (`robustLinearFit`) used to rescale Boone's values onto DraftSharks' scale, with outlier clipping via median absolute deviation. This is the statistical core of the blending step.
- **`trends.ts`** — computes week-over-week deltas for the Trends view.
- **`vorp.ts`** — Value Over Replacement Player: given league settings (team count, roster slots per position), computes a "replacement level" value per position and expresses each player's value relative to that baseline.
- **`weeks.ts`** — helpers for tracking which weeks of data exist and which is "active."

### `src/state/store.ts`
A single global Zustand store holding everything: blend weights, which sources are enabled, all uploaded data organized by week, league settings, saved team/roster profiles, and various toggles (bye-week penalty, handcuff policy, "elite premium," whether K/DST are included). This is the one place that owns app-wide state; components read from and write to it rather than passing props around.

### `src/types.ts`
Shared TypeScript types (`SourceRow`, `BlendedRow`, `LeagueSettings`, `TeamProfile`, `PPR`, etc.) that tie the modules above together.

## `scrapers/` — standalone data-pulling scripts (separate from the web app)

- **`boone.py`** — browser-automation scraper that pulls Boone's weekly rankings (Boone's site apparently requires clicking through UI states — the `data/debug/` folder is full of screenshots/HTML dumps captured while building this, showing the trial-and-error involved).
- **`draftsharks.py`** — scraper for DraftSharks' weekly rankings.
- **`debug_boone.py`** — a debugging/inspection variant of the Boone scraper.
- **`run_all.py`** / **`run_all.bat`** — runs both scrapers in sequence.
- **`data/`** — output CSVs from past scraper runs (both sources, several past weeks, plus half-PPR/full-PPR variants for DraftSharks), and a `debug/` subfolder of scraper development artifacts. This is scraped output, not source code — treat it as historical/disposable.
