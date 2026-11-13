#!/usr/bin/env python
"""Builds the canonical_name+position -> ESPN athlete id lookup used for site headshots.

Source: ESPN's public team-roster API (all 32 teams). Headshot URL on the site is
https://a.espncdn.com/i/headshots/nfl/players/full/<espn_id>.png

Usage:
    python scripts/build_player_images.py            # dry run: coverage report only
    python scripts/build_player_images.py --push     # upsert into Supabase player_images

Players not on a current ESPN roster (free agents, UNS) simply have no row and the
site falls back to initials. Overrides for stubborn name mismatches go in
data/player_image_overrides.csv (canonical_name,position,espn_id).
"""
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src import paths
from src.player_identity import normalize_name

BASE_DIR = Path(__file__).resolve().parent.parent
OVERRIDES = BASE_DIR / "data" / "player_image_overrides.csv"
API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
POS_MAP = {"FB": "RB", "PK": "K"}


def fetch_espn() -> dict[tuple[str, str], str]:
    teams = requests.get(f"{API}/teams", timeout=30).json()["sports"][0]["leagues"][0]["teams"]
    out: dict[tuple[str, str], str] = {}
    for t in teams:
        tid = t["team"]["id"]
        # Defenses: canonical_name is the full team name, position DST. The
        # site draws the team logo for ids prefixed "team:".
        out[(normalize_name(t["team"]["displayName"]), "DST")] = "team:" + t["team"]["abbreviation"].lower()
        roster = requests.get(f"{API}/teams/{tid}/roster", timeout=30).json()
        for group in roster.get("athletes", []):
            for a in group.get("items", []):
                pos = a.get("position", {}).get("abbreviation", "")
                pos = POS_MAP.get(pos, pos)
                out[(normalize_name(a["fullName"]), pos)] = str(a["id"])
    return out


def load_overrides() -> dict[tuple[str, str], str]:
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(newline="", encoding="utf-8") as f:
        return {(r["canonical_name"], r["position"]): r["espn_id"] for r in csv.DictReader(f)}


def pool_from_csvs() -> set[tuple[str, str]]:
    pool: set[tuple[str, str]] = set()
    for p in (paths.PROCESSED_DIR / "trade_values_long.csv", paths.PROCESSED_DIR / "ros_rankings_long.csv"):
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["position"] in ("QB", "RB", "WR", "TE", "DST"):
                    pool.add((normalize_name(r["canonical_name"]), r["position"]))
    return pool


def load_env() -> None:
    env = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    push = "--push" in sys.argv
    espn = fetch_espn()
    espn.update(load_overrides())
    print(f"ESPN roster entries: {len(espn)}")

    pool = pool_from_csvs()
    matched = {k: espn[k] for k in pool if k in espn}
    # Nickname fallback (cameron/cam, matthew/matt ...): same position and last
    # name, one first name a prefix of the other, only if exactly one candidate.
    for n, pos in sorted(pool - set(matched)):
        first, _, last = n.partition(" ")
        cands = [(en, i) for (en, ep), i in espn.items()
                 if ep == pos and en.partition(" ")[2] == last and last
                 and (en.startswith(first[:3]) and (en.partition(" ")[0].startswith(first)
                      or first.startswith(en.partition(" ")[0])))]
        if len(cands) == 1:
            matched[(n, pos)] = cands[0][1]
            espn[(n, pos)] = cands[0][1]
            print(f"  nickname match: {n} -> {cands[0][0]}")
    missing = sorted(pool - set(matched))
    print(f"Pool (local CSVs): {len(pool)}  matched: {len(matched)}  unmatched: {len(missing)}")
    if missing:
        print("Unmatched (first 60):", ", ".join(f"{n}|{p}" for n, p in missing[:60]))

    if not push:
        print("Dry run -- nothing written. Re-run with --push to upsert.")
        return

    load_env()
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    # Push the entire ESPN set, not just today's pool: players enter the pool later.
    rows = [{"canonical_name": n, "position": p, "espn_id": i} for (n, p), i in espn.items()]
    for i in range(0, len(rows), 500):
        r = requests.post(
            f"{url}/rest/v1/player_images?on_conflict=canonical_name,position",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=rows[i:i + 500], timeout=60,
        )
        r.raise_for_status()
    print(f"Upserted {len(rows)} rows.")


if __name__ == "__main__":
    main()
