#!/usr/bin/env python
"""Pulls weekly rankings from one or more sources and writes them to
data/raw/ (immutable snapshot) and data/processed/rankings_long.csv (append).

Usage:
    python scripts/pull_week.py                          # every active week, all sources, both scorings
    python scripts/pull_week.py --week 2                  # just week 2
    python scripts/pull_week.py --week 1,2 --source boone
    python scripts/pull_week.py --week all --scoring half-ppr

"--week all" (also the default) pulls every week from the current one through
the end of the season for Draft Sharks (which does publish future weeks) --
see src/season_config.py. Boone/Smyth only ever publish the CURRENT week, so
under "--week all" they're only attempted for that one week, not every future
week (that would just be a permanent, expected "zero rows" failure every day
for the rest of the season -- noise that buries a real failure). Pass an
explicit --week to override this and force a check anyway. A week already
fully played is never pulled automatically; re-pull it explicitly with
--week N if you ever need to.

Exits non-zero if any pull has a validation error or an unexpected failure --
treat that as "this run needs attention," not a warning to skim past. Every
run also writes data/last_run_status.json (source/scoring/week -> ok|failed)
so an external check (cron output, a scheduled task, a monitoring script) can
tell success from failure without parsing console text.
"""

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Windows' default console codepage (cp1252) can't encode the emoji in this
# script's console output (jared-scrapers convention) -- force UTF-8 stdout
# rather than dropping the convention.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import normalize, season_config, storage, validate
from src.sources.draftsharks_weekly import DraftSharksFetchError, fetch_draftsharks_weekly
from src.sources.yahoo_weekly_consensus import YahooConsensusFetchError, fetch_expert_weekly

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "rankings_long.csv"
STATUS_PATH = BASE_DIR / "data" / "last_run_status.json"

ALL_SOURCES = ["draftsharks", "boone", "smythe"]
YAHOO_EXPERT_NAMES = {"boone": "Justin Boone", "smythe": "Joel Smyth"}


def fetch_and_normalize(source: str, week: int, season: int, scoring: str, pulled_at: str):
    if source == "draftsharks":
        raw = fetch_draftsharks_weekly(week=week, scoring_slug=scoring)
        return raw, normalize.draftsharks_to_ranking_rows(raw, season, week, scoring, pulled_at)
    if source in YAHOO_EXPERT_NAMES:
        raw = fetch_expert_weekly(
            YAHOO_EXPERT_NAMES[source], week=week, year=season, scoring_slug=scoring
        )
        return raw, normalize.yahoo_expert_to_ranking_rows(
            raw, source, season, week, scoring, pulled_at
        )
    raise ValueError(f"Unknown source: {source}")


def parse_weeks(raw: str) -> list[int]:
    if raw == "all":
        return season_config.active_weeks()
    return [int(w) for w in raw.split(",")]


def build_combos(
    weeks: list[int], sources: list[str], scorings: list[str],
    current_week: int, restrict_yahoo_to_current: bool,
) -> list[tuple[int, str, str]]:
    """Boone/Smyth (Yahoo) never publish a future week's rankings -- only the
    current one. Pulling them for every future week anyway (as "--week all"
    naively would) doesn't just waste requests: it means EVERY unattended run
    reports the same "zero rows" failures for every week beyond the current
    one, forever -- permanent noise that buries a real failure instead of
    surfacing it. So under "--week all" (restrict_yahoo_to_current=True),
    Boone/Smyth are only attempted for the current week; an explicit --week
    list still tries whatever was asked for, since that's a deliberate manual
    check (e.g. "has Boone posted week 5 yet?"), not the automated default."""
    combos = []
    for week in weeks:
        for source in sources:
            if restrict_yahoo_to_current and source in YAHOO_EXPERT_NAMES and week != current_week:
                continue
            for scoring in scorings:
                combos.append((week, source, scoring))
    return combos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--week", default="all",
        help='Comma list of week numbers, or "all" (default) for every '
             "active week through end of season (src/season_config.py).",
    )
    parser.add_argument("--season", type=int, default=season_config.SEASON)
    parser.add_argument("--source", default="all", help="Comma list, or 'all'")
    parser.add_argument("--scoring", default="half-ppr,ppr", help="Comma list")
    args = parser.parse_args()

    weeks = parse_weeks(args.week)
    sources = ALL_SOURCES if args.source == "all" else args.source.split(",")
    scorings = args.scoring.split(",")
    combos = build_combos(
        weeks, sources, scorings,
        current_week=season_config.current_week(),
        restrict_yahoo_to_current=(args.week == "all"),
    )

    start = datetime.now()
    pulled_at = start.astimezone(timezone.utc).isoformat(timespec="seconds")
    total = len(combos)
    print(f"Starting pull -- weeks {weeks[0]}-{weeks[-1]}, {total} combo(s)")
    print(f"   {start.strftime('%H:%M:%S')}\n")

    results = {}  # (week, source, scoring) -> normalized rows, for cross-source comparison
    run_status = {}  # "week{N}/{source}/{scoring}" -> "ok" | "failed: <reason>"
    success_count = 0
    any_errors = False

    for i, (week, source, scoring) in enumerate(combos, 1):
        label = f"week {week} / {source} / {scoring}"
        status_key = f"week{week}/{source}/{scoring}"
        print(f"[{i}/{total}] {label}...")
        try:
            raw, rows = fetch_and_normalize(source, week, args.season, scoring, pulled_at)
        except (DraftSharksFetchError, YahooConsensusFetchError, ValueError) as e:
            print(f"\n❌ Failed on: {label}")
            print(f"   Reason: {e}")
            any_errors = True
            run_status[status_key] = f"failed: {e}"
            continue
        except Exception as e:
            print(f"\n❌ Unexpected failure on: {label}")
            print(f"   Reason: {e}")
            traceback.print_exc()
            run_status[status_key] = f"failed: unexpected error: {e}"
            _write_status(run_status)
            sys.exit(1)

        rows, dedupe_issues = validate.dedupe_players(rows)

        compare_against = None
        if source == "smythe" and (week, "boone", scoring) in results:
            compare_against = results[(week, "boone", scoring)]
        elif source == "boone" and (week, "smythe", scoring) in results:
            compare_against = results[(week, "smythe", scoring)]

        issues = dedupe_issues + validate.validate_pull(
            rows,
            compare_against=compare_against,
            expect_projection=(source == "draftsharks"),
        )
        for issue in issues:
            icon = "❌" if issue.severity == "error" else "⚠️ "
            print(f"   {icon} {issue.message}")
        if validate.has_errors(issues):
            any_errors = True
            run_status[status_key] = "failed: " + "; ".join(
                i.message for i in issues if i.severity == "error"
            )
            print(f"   Not writing output for {label} -- validation failed.")
            continue

        snapshot_path = storage.raw_snapshot_path(RAW_DIR, source, args.season, week, scoring, pulled_at)
        storage.write_raw_snapshot(snapshot_path, raw)
        storage.append_processed(PROCESSED_PATH, rows)
        results[(week, source, scoring)] = rows
        run_status[status_key] = "ok"
        success_count += 1
        print(f"   {len(rows)} rows -> {snapshot_path.relative_to(BASE_DIR)}")

    elapsed = datetime.now() - start
    mins, secs = elapsed.seconds // 60, elapsed.seconds % 60
    print(f"\n{'=' * 45}")
    print(f"{'✅' if not any_errors else '⚠️ '} Done: {success_count}/{total} combo(s) written")
    print(f"⏱  Time: {mins}m {secs}s")
    print(f"\U0001f4c1 Processed output: {PROCESSED_PATH.resolve()}")
    if any_errors:
        failed = [k for k, v in run_status.items() if v != "ok"]
        print(f"⚠️  Failed combos ({len(failed)}): {', '.join(failed)}")
    print(f"{'=' * 45}")

    _write_status(run_status, any_errors=any_errors)

    if any_errors:
        sys.exit(1)


def _write_status(run_status: dict, any_errors: bool = True) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ok": not any_errors,
                "combos": run_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
