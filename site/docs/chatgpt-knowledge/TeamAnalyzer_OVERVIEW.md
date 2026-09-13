# Team Analyzer — Overview

## What this is

Team Analyzer is a browser-based fantasy football trade-value tool Jared built last season (a "v1 core," per its own README). It lives at `in-season/site/` — it was moved there recently as part of consolidating his fantasy football tools under one `in-season/` folder, but it's a self-contained project with its own history, not something built alongside the new in-season pipeline. It hasn't been updated for the current season yet and is expected to need rework before it's used again.

The core idea: take two competing sets of expert player rankings — "Boone" (Justin Boone, an independent fantasy analyst) and "DraftSharks" — and blend them into one trade-value number per player, so Jared can evaluate trades and build his roster around a value that isn't fully dependent on trusting a single source.

## Why it exists

Different fantasy ranking sources disagree, sometimes a lot, and they're not on the same numeric scale — one source might rate players from 1-300, another might use a totally different point system. Rather than picking one source and hoping it's right, or eyeballing multiple spreadsheets side by side, Team Analyzer:

1. Takes weekly CSV exports from both sources.
2. Statistically re-scales Boone's numbers onto DraftSharks' scale (since DraftSharks is treated as the "anchor") using a robust linear regression that throws out outliers.
3. Blends the two scaled sets together with a configurable weight (default: 60% DraftSharks / 40% Boone).
4. Surfaces that blended number in a few different views: a sortable player table, week-over-week trend tracking (who's rising/falling), a roster analyzer, and an early "trade sandbox" for comparing what each side of a trade is worth.

## Architecture, in plain terms

It's a single-page web app (React + TypeScript, built with Vite) that runs entirely in the browser — there's no backend server and no database. All the data Jared uploads and all his settings are kept in the browser's local storage, so it's tied to one browser/machine unless he exports something.

The app is organized as a few conceptual layers:
- **Ingestion**: CSV upload and parsing, tolerant of some variation in column naming across weekly export files from each source.
- **Blending engine**: the regression-based scale-matching and weighted blend described above, applied per week.
- **Analysis views**: tabs for browsing blended/raw player values, viewing trends over time, analyzing a saved roster, and a trade comparison sandbox.
- **Settings/state**: league settings (roster slots, scoring type, team count) that feed into value-over-replacement-style calculations, all held in a global client-side store.

This project previously had its own `scrapers/` folder with standalone Python scripts that pulled the Boone and DraftSharks CSVs automatically instead of exporting them by hand. That folder has been removed; automated data pulling is now handled by the `in-season` pipeline (see below) rather than a separate scraping path within this project.

## Status relative to the new in-season pipeline

This predates and duplicates part of what the new `in-season/` weekly-rankings pipeline (see the main in-season knowledge files) now does more robustly — that pipeline already pulls Boone and DraftSharks weekly rankings on a schedule with validation. Team Analyzer's own (now-removed) scrapers were a rougher, earlier version of that same idea. Any future rework of Team Analyzer should consume the new pipeline's data (e.g. via Supabase) rather than reviving a separate scraping path — but that decision hasn't been made yet; for now this file just documents what exists.
