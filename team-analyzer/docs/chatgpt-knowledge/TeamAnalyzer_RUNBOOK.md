# Team Analyzer — Runbook

## Running the app locally

From `in-season/team-analyzer/`:

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

## Producing those CSVs via the scrapers (optional, alternate path)

Instead of manually exporting from each source's site, the `scrapers/` folder has Python scripts that attempt to pull the data automatically:

```bash
cd scrapers
python run_all.py
```

This is browser-automation-based for Boone and more likely to break if either source's site changes layout — the `data/debug/` folder full of screenshots suggests this needed real trial-and-error to get working last time. **This has not been verified to still work** — it hasn't been run or checked since last season, and the new `in-season/` pipeline (see that project's own runbook) now does something similar more reliably. If reviving Team Analyzer, it's worth checking whether it makes more sense to feed it from that pipeline's output instead of re-running these scrapers.

## Common things to check when something looks wrong

- **A player's value looks off** — check whether their name matched correctly between sources (`src/lib/names.ts` handles name normalization; mismatches would show up as one source's value going unused for that player).
- **Values across weeks look inconsistent** — the regression-based Boone-to-DraftSharks scaling (`src/lib/regression.ts`) runs fresh per week, so a bad week for one source's rankings can shift the fit; there's no cross-week smoothing.
- **Nothing loads after upload** — likely a CSV column-naming mismatch (`src/lib/sources.ts` lists the exact column names it looks for); check the uploaded file's headers against those.
