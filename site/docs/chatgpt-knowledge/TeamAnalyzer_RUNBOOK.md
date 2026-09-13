# Team Analyzer — Runbook

## Running the app locally

From `in-season/site/`:

```bash
npm i
npm run dev
```

(The README also lists `pnpm` equivalents — either works, but check which lockfile is present before mixing package managers; there's a `package-lock.json`, suggesting npm is the one actually in use.)

This starts a Vite dev server; open the printed local URL in a browser. There is no backend to start separately — everything runs client-side.

## Building for deployment

```bash
npm run build
```

This runs a TypeScript build check (`tsc -b`) then a Vite production build. The README notes this is meant to be deployed as a static app on Vercel (`vercel.json` is already configured for that), but nothing indicates it's currently deployed anywhere live — treat it as "buildable" rather than "deployed."

## Getting data into it

The app expects two CSV files per week, uploaded through its UI (drag a folder):
- A **Boone** export, with columns like `PosRank, Name, 0.5ppr, 1ppr` (older format) or `Position, half_ppr, full_ppr` (newer format) — the code tries to handle both.
- A **DraftSharks** export, with columns like `Name, Pos, 0.5ppr_value, 1ppr_value` or `half_ppr, full_ppr`.

File names need to include the week number and which source it is (e.g. something containing `week3` and `boone`, case-insensitive) — the app auto-detects the week from the filename.

## Producing those CSVs automatically (optional, alternate path)

Instead of manually exporting from each source's site, data now comes from the `in-season` Python pipeline (see that project's own runbook), which pulls Boone and DraftSharks weekly rankings on a schedule. The standalone scrapers that used to live in this project's own `scrapers/` folder have been removed in favor of that pipeline; if reviving Team Analyzer, feed it from the pipeline's output rather than writing new scraping scripts here.

## Common things to check when something looks wrong

- **A player's value looks off** — check whether their name matched correctly between sources (`src/lib/names.ts` handles name normalization; mismatches would show up as one source's value going unused for that player).
- **Values across weeks look inconsistent** — the regression-based Boone-to-DraftSharks scaling (`src/lib/regression.ts`) runs fresh per week, so a bad week for one source's rankings can shift the fit; there's no cross-week smoothing.
- **Nothing loads after upload** — likely a CSV column-naming mismatch (`src/lib/sources.ts` lists the exact column names it looks for); check the uploaded file's headers against those.
