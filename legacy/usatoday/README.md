# USA Today trade values (retired 2026-10-07)

usatoday.com returns 402 "Access Restricted" (TollBit token required) to automated clients, including a normal browser session, so the weekly pull could no longer discover or fetch the article. Removed from `scripts/scheduled_pull.ps1`.

Archived here: the pull script, source module, tests, `normalize_usatoday.py` (the normalizer removed from `src/normalize.py`) and the last status file. Imports point at the old locations; move files back to `scripts/`, `src/sources/`, `tests/` and restore the normalizer to revive it. Past weeks' rows stay in `trade_values_long.csv` and Supabase.
