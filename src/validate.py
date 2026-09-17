"""Validation for a single pull's rows -- catches failed, incomplete, or
suspicious pulls per Jared's explicit requirement that a bad week surface
loudly rather than get silently written as if it were good data.

Two severities: "error" (pull should not be trusted / written -- pull_week.py
exits non-zero) and "warning" (worth a human glance, not a hard stop).
"""

from dataclasses import dataclass

from src.schema import RankingRow, RosRankingRow, TradeValueRow

# Rough floors, not exact expected counts -- a full weekly pull (all
# positions) should clear these by a wide margin; anything below suggests a
# partial/broken scrape rather than a genuinely thin position group.
MINIMUM_POSITION_COUNTS = {
    "QB": 20, "RB": 30, "WR": 30, "TE": 10,
}


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    message: str


def check_nonempty(rows: list[RankingRow]) -> list[ValidationIssue]:
    if not rows:
        return [ValidationIssue("error", "Pull returned zero rows.")]
    return []


def check_required_fields(
    rows: list[RankingRow], expect_projection: bool = True
) -> list[ValidationIssue]:
    issues = []
    missing_name = sum(1 for r in rows if not r.player_name)
    missing_position = sum(1 for r in rows if not r.position)
    if missing_name:
        issues.append(ValidationIssue(
            "error", f"{missing_name}/{len(rows)} rows have a blank player_name."
        ))
    if missing_position:
        issues.append(ValidationIssue(
            "error", f"{missing_position}/{len(rows)} rows have a blank position."
        ))
    if expect_projection:
        missing_projection = sum(1 for r in rows if r.projection is None)
        if missing_projection > len(rows) * 0.5:
            issues.append(ValidationIssue(
                "warning",
                f"{missing_projection}/{len(rows)} rows have no projection value "
                "-- more than half. Check the source response shape.",
            ))
    return issues


def dedupe_players(rows: list[RankingRow]) -> tuple[list[RankingRow], list[ValidationIssue]]:
    """Drops repeat appearances of the same player within one pull, keeping
    the first (typically the better rank). Confirmed live 2026-09-09: Draft
    Sharks' own Week 2 half-PPR page genuinely lists a player twice at two
    different ranks (Geno Smith, id 6653, ranks 37 and 38) -- a site-side
    rendering bug, not a pagination/dedup bug in this fetcher. Blocking an
    entire otherwise-good ~870-row pull over one glitchy player defeats the
    "keep this running unattended" goal, so this drops the dupe(s) and
    returns a warning rather than failing the whole pull -- call this BEFORE
    validate_pull so check_no_duplicate_players (a safety net, not the
    primary defense) sees clean data."""
    seen: dict[str, str] = {}
    deduped: list[RankingRow] = []
    dropped: dict[str, str] = {}
    for r in rows:
        key = r.source_player_id or r.player_name
        if key in seen:
            dropped[key] = r.player_name
            continue
        seen[key] = r.player_name
        deduped.append(r)

    if not dropped:
        return rows, []

    names = [f"{name} ({key})" for key, name in list(dropped.items())[:10]]
    issue = ValidationIssue(
        "warning",
        f"{len(dropped)} duplicate player row(s) dropped (kept the first "
        f"occurrence): {', '.join(names)}{', ...' if len(dropped) > 10 else ''}. "
        "Observed as a genuine source-site bug, not necessarily a scraper "
        "bug -- worth a glance if it keeps recurring.",
    )
    return deduped, [issue]


def check_no_duplicate_players(rows: list[RankingRow]) -> list[ValidationIssue]:
    """Safety net only -- callers are expected to run dedupe_players() first.
    If this ever fires, dedupe_players wasn't called (a real bug), not a
    Draft-Sharks-site quirk, so this stays a hard error."""
    seen: set[str] = set()
    dupes: set[str] = set()
    for r in rows:
        key = r.source_player_id or r.player_name
        if key in seen:
            dupes.add(key)
        seen.add(key)
    if dupes:
        return [ValidationIssue(
            "error",
            f"{len(dupes)} player(s) still duplicated after dedupe_players() -- "
            f"{sorted(dupes)[:10]}{'...' if len(dupes) > 10 else ''}. This means "
            "dedupe_players() wasn't called before validate_pull(), not a "
            "source-site quirk -- check the caller.",
        )]
    return []


def check_position_counts(
    rows: list[RankingRow], floors: dict[str, int] = MINIMUM_POSITION_COUNTS
) -> list[ValidationIssue]:
    issues = []
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.position] = counts.get(r.position, 0) + 1
    for position, floor in floors.items():
        actual = counts.get(position, 0)
        if actual < floor:
            issues.append(ValidationIssue(
                "warning",
                f"Only {actual} {position} rows (expected at least {floor}) "
                "-- may be a partial pull.",
            ))
    return issues


def check_not_identical_to_other_source(
    rows: list[RankingRow],
    other_rows: list[RankingRow],
    top_n: int = 10,
    max_shared_fraction: float = 0.8,
) -> list[ValidationIssue]:
    """Flags a pull whose top-N player order is suspiciously close to another
    source's pull for the same week/scoring -- the specific failure mode
    observed with Smyth's (unconfirmed) expert id possibly falling back to
    Boone's data. A real match at the very top of one position is plausible
    consensus, not proof of failure -- this only warns, never errors, and
    only when the overlap is broad (checked across positions, not one)."""
    by_position_a = _top_n_by_position(rows, top_n)
    by_position_b = _top_n_by_position(other_rows, top_n)
    shared_positions = set(by_position_a) & set(by_position_b)
    if not shared_positions:
        return []

    identical = sum(
        1 for pos in shared_positions if by_position_a[pos] == by_position_b[pos]
    )
    fraction = identical / len(shared_positions)
    if fraction >= max_shared_fraction:
        return [ValidationIssue(
            "warning",
            f"Top-{top_n} player order is identical to the other source in "
            f"{identical}/{len(shared_positions)} positions -- possible "
            "expert-id fallback rather than genuinely independent rankings. "
            "Spot-check before trusting this pull.",
        )]
    return []


def _top_n_by_position(rows: list[RankingRow], top_n: int) -> dict[str, tuple]:
    by_position: dict[str, list[RankingRow]] = {}
    for r in rows:
        by_position.setdefault(r.position, []).append(r)
    return {
        pos: tuple(r.player_name for r in sorted(rs, key=lambda r: r.rank or 9999)[:top_n])
        for pos, rs in by_position.items()
    }


def validate_pull(
    rows: list[RankingRow],
    position_floors: dict[str, int] | None = None,
    compare_against: list[RankingRow] | None = None,
    expect_projection: bool = True,
) -> list[ValidationIssue]:
    """Runs every check and returns the combined issue list. Callers decide
    what to do with it; pull_week.py treats any "error" issue as fatal."""
    issues: list[ValidationIssue] = []
    issues += check_nonempty(rows)
    if not rows:
        return issues  # every other check assumes at least one row
    issues += check_required_fields(rows, expect_projection=expect_projection)
    issues += check_no_duplicate_players(rows)
    issues += check_position_counts(rows, position_floors or MINIMUM_POSITION_COUNTS)
    if compare_against:
        issues += check_not_identical_to_other_source(rows, compare_against)
    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)


MINIMUM_TRADE_VALUE_COUNTS = {"QB": 15, "RB": 30, "WR": 30, "TE": 8}


def validate_trade_values(
    rows: list[TradeValueRow], position: str, floor: int | None = None
) -> list[ValidationIssue]:
    if not rows:
        return [ValidationIssue(
            "error", f"Trade value pull for {position} returned zero rows."
        )]
    issues: list[ValidationIssue] = []
    missing_name = sum(1 for r in rows if not r.player_name)
    if missing_name:
        issues.append(ValidationIssue(
            "error",
            f"{missing_name}/{len(rows)} {position} trade-value rows have a "
            "blank player_name.",
        ))
    effective_floor = floor if floor is not None else MINIMUM_TRADE_VALUE_COUNTS.get(position, 5)
    if len(rows) < effective_floor:
        issues.append(ValidationIssue(
            "warning",
            f"Only {len(rows)} {position} trade-value rows (expected at "
            f"least {effective_floor}) -- may be a partial pull.",
        ))
    return issues


def validate_ros_rankings(
    rows: list[RosRankingRow],
    position_floors: dict[str, int] | None = None,
) -> list[ValidationIssue]:
    """Validates one scoring slug's Draft Sharks ROS pull. Mirrors
    validate_pull (all positions pulled in one call, same shape as weekly
    rankings) rather than validate_trade_values (per-position pulls)."""
    if not rows:
        return [ValidationIssue("error", "ROS rankings pull returned zero rows.")]
    issues: list[ValidationIssue] = []
    missing_name = sum(1 for r in rows if not r.player_name)
    missing_position = sum(1 for r in rows if not r.position)
    if missing_name:
        issues.append(ValidationIssue(
            "error", f"{missing_name}/{len(rows)} rows have a blank player_name."
        ))
    if missing_position:
        issues.append(ValidationIssue(
            "error", f"{missing_position}/{len(rows)} rows have a blank position."
        ))
    issues += check_position_counts(rows, position_floors or MINIMUM_POSITION_COUNTS)
    return issues
