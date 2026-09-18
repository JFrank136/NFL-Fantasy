"""Resolves a canonical player name for rows the in-season pipeline ingests.

Uses Draft/data/aliases.csv as the alias source of truth (the same file
Draft/src/matching.py and Vampire's src/name-matching.js already read
independently). That file is keyed by (raw_name, raw_team, source) where
`source` means the SITE that spelled a name a certain way ("yahoo",
"footballguys") -- not a fantasy-analyst source. None of in-season's own
sources (draftsharks, boone, smythe) ever appear in that column, so a
source-scoped lookup would never match anything here. Matching instead
ignores source/team entirely and keys purely on normalized name -- the file
is small (~20 rows) and curated, so name-only collisions aren't a practical
risk.

This does not fully solve cross-dataset name-matching gaps (e.g. a player
missing entirely from one source's pull) -- seeing docs/superpowers/specs/
2026-09-12-supabase-foundation-design.md for what's explicitly out of scope.
"""

import csv
from pathlib import Path

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "Draft" / "data" / "aliases.csv"

_aliases_cache: dict[str, str] | None = None


def normalize_name(raw_name: str) -> str:
    name = raw_name.lower().strip()
    # Strip straight (') AND curly ('  U+2018, '  U+2019) apostrophes --
    # sources spell names like "Ja'Marr Chase" / "Ja'Marr Chase"
    # inconsistently, and treating them as different characters silently
    # split one player into two canonical_name rows (confirmed live
    # 2026-09-18: Trade Values pivot showed Ja'Marr Chase and D'Andre Swift
    # each twice, one copy missing data the other had).
    name = name.replace(".", "").replace("'", "").replace("‘", "").replace("’", "")
    name = name.replace("-", " ")
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens)


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, str]:
    """normalized raw_name -> canonical_name, deduped across all rows
    regardless of source/team (see module docstring for why)."""
    aliases: dict[str, str] = {}
    if not path.exists():
        return aliases
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aliases[normalize_name(row["raw_name"])] = row["canonical_name"]
    return aliases


def canonical_name_for(raw_name: str, aliases: dict[str, str] | None = None) -> str:
    """Resolves `raw_name` to its canonical form. Uses the cached real
    aliases.csv by default; pass `aliases` explicitly in tests to avoid
    depending on that file's live content."""
    global _aliases_cache
    if aliases is None:
        if _aliases_cache is None:
            _aliases_cache = load_aliases()
        aliases = _aliases_cache
    norm = normalize_name(raw_name)
    return aliases.get(norm, norm)
