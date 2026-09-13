#!/usr/bin/env python3
"""
Action Network Super Bowl picks scraper (hub page -> game preview -> Next.js JSON -> CSV).

Usage:
  py scrape_action_superbowl.py --hub-url "https://www.actionnetwork.com/nfl/picks/game"

Optional:
  --choose "Chiefs"   (pick the first game card containing this text)
  --out data/action_network_superbowl.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

DEFAULT_OUT = os.path.join("data", "action_network_superbowl.csv")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def extract_build_id(html: str) -> str:
    m = re.search(r"/_next/data/([^/]+)/", html)
    if m:
        return m.group(1)
    m2 = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
    if m2:
        return m2.group(1)
    raise ValueError("Could not find Next.js buildId in HTML.")


def parse_game_slug_and_id(game_url: str) -> Tuple[str, int]:
    p = urlparse(game_url)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        raise ValueError(f"URL path too short to contain slug/gameId: {p.path}")
    game_id_str = parts[-1]
    slug = parts[-2]
    if not game_id_str.isdigit():
        raise ValueError(f"Expected last URL segment to be numeric gameId, got: {game_id_str}")
    return slug, int(game_id_str)


def make_next_data_url(build_id: str, slug: str, game_id: int) -> str:
    return (
        f"https://www.actionnetwork.com/_next/data/{build_id}/nfl-game/{slug}/{game_id}.json"
        f"?league=nfl-game&slug={slug}&gameId={game_id}"
    )


def safe_get(d: Dict[str, Any], *keys: str, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def classify_market_type(pick: Dict[str, Any]) -> str:
    # If Action provides a bet_type, use it
    bet_type = (pick.get("bet_type") or "").lower()
    if bet_type in {"spread", "total", "ml", "moneyline", "props", "prop"}:
        return "ml" if bet_type == "moneyline" else bet_type

    # Otherwise infer from custom_pick_rules if present
    rules = pick.get("custom_pick_rules") or {}
    bt = (rules.get("bet_type") or "").lower()
    if bt in {"spread", "total", "ml", "moneyline"}:
        return "ml" if bt == "moneyline" else bt

    # Heuristic: most custom player lines are props
    play = (pick.get("play") or "").lower()
    if re.search(r"\b[ou]\s*\d+(\.\d+)?\b", play):
        return "props"

    return "unknown"


def compute_unique_key(game_id: Any, expert_id: Any, pick_id: Any) -> str:
    raw = f"{game_id}_{expert_id}_{pick_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_existing_keys(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    keys = set()
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "unique_key" not in (reader.fieldnames or []):
            return set()
        for row in reader:
            k = row.get("unique_key")
            if k:
                keys.add(k)
    return keys


def iter_rows_from_payload(payload: Dict[str, Any], source_url: str) -> List[Dict[str, Any]]:
    game = safe_get(payload, "pageProps", "game", default={})
    experts = game.get("experts") or []

    game_id = game.get("id")
    league = game.get("league_name") or game.get("league") or None
    scraped_at = utc_now_iso()

    rows: List[Dict[str, Any]] = []

    for expert in experts:
        if not isinstance(expert, dict):
            continue

        expert_id = expert.get("id")
        source_name = expert.get("name")
        source_username = expert.get("username")

        record = expert.get("record") or {}
        expert_record_win = record.get("win")
        expert_record_loss = record.get("loss")
        expert_record_push = record.get("push")
        expert_units_net = record.get("units_net")

        picks = expert.get("picks") or []
        for pick in picks:
            if not isinstance(pick, dict):
                continue

            pick_id = pick.get("id")
            unique_key = compute_unique_key(game_id, expert_id, pick_id)

            rows.append({
                # Source / capper
                "source_name": source_name,
                "source_username": source_username,
                "expert_units_net": expert_units_net,
                "expert_record_win": expert_record_win,
                "expert_record_loss": expert_record_loss,
                "expert_record_push": expert_record_push,

                # Pick details
                "market_type": classify_market_type(pick),
                "bet_label": pick.get("play"),
                "line": pick.get("value"),
                "odds": pick.get("odds"),
                "stake_units": pick.get("units"),
                "units_type": pick.get("units_type"),
                "prop_name": pick.get("custom_pick_name") or pick.get("custom_pick_full_name") or None,
                "notes": safe_get(pick, "meta", "note", default=None),

                # IDs / timing
                "game_id": pick.get("game_id") or game_id,
                "league": pick.get("league_name") or league,
                "pick_id": pick_id,
                "expert_id": expert_id,
                "created_at": pick.get("created_at"),
                "updated_at": pick.get("updated_at"),

                # Tracking
                "scraped_at": scraped_at,
                "source_url": source_url,
                "unique_key": unique_key,
            })

    return rows


def fetch_game_payload_from_game_url(game_url: str, timeout: int = 30) -> Tuple[Dict[str, Any], str]:
    # Load game page HTML to get buildId
    r = requests.get(game_url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    build_id = extract_build_id(r.text)

    slug, game_id = parse_game_slug_and_id(game_url)
    data_url = make_next_data_url(build_id, slug, game_id)

    j = requests.get(data_url, headers=HEADERS, timeout=timeout)
    j.raise_for_status()
    return j.json(), data_url


def append_new_rows(csv_path: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    ensure_parent_dir(csv_path)
    existing = load_existing_keys(csv_path)
    new_rows = [r for r in rows if r.get("unique_key") not in existing]
    if not new_rows:
        return 0

    fieldnames = list(new_rows[0].keys())
    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerows(new_rows)

    return len(new_rows)


def get_superbowl_game_preview_url(hub_url: str, choose_contains: Optional[str] = None, headless: bool = True) -> str:
    """
    NEW approach (no modal):
    - Open hub page
    - Extract the first /nfl-game/ link (or one matching choose_contains text)
    - Return fully-qualified URL.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError(
            "Playwright is required for hub-url discovery. Install with:\n"
            "  py -m pip install playwright\n"
            "  py -m playwright install chromium\n"
        ) from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(hub_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2000)

        # Strategy:
        # The hub already contains direct links to /nfl-game/<slug>/<gameId>.
        # We'll take the first one, or one whose surrounding text contains choose_contains.
        game_links = page.locator("a[href*='/nfl-game/']")

        if game_links.count() == 0:
            browser.close()
            raise RuntimeError("No /nfl-game/ links found on hub page. Site layout may have changed.")

        chosen_href = None

        if choose_contains:
            # Find the first /nfl-game/ link whose visible text contains the choose string
            for i in range(min(game_links.count(), 50)):
                el = game_links.nth(i)
                txt = (el.inner_text() or "").strip().lower()
                if choose_contains.lower() in txt:
                    chosen_href = el.get_attribute("href")
                    break

        if not chosen_href:
            chosen_href = game_links.first.get_attribute("href")

        browser.close()

    if not chosen_href:
        raise RuntimeError("Found /nfl-game/ link elements but could not read href attribute.")

    if chosen_href.startswith("http"):
        return chosen_href

    # Make absolute
    return "https://www.actionnetwork.com" + chosen_href


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-url", required=True, help="https://www.actionnetwork.com/nfl/picks/game")
    ap.add_argument("--choose", default=None, help='Optional text to pick a specific game card (e.g., "Chiefs")')
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"CSV output path (default: {DEFAULT_OUT})")
    ap.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    ap.add_argument("--headed", action="store_true", help="Run Playwright headed (visible browser) for debugging")
    args = ap.parse_args()

    # Step 1: discover the game URL from the hub (Super Bowl -> modal -> Game Preview)
    try:
        game_url = get_superbowl_game_preview_url(args.hub_url, choose_contains=args.choose, headless=not args.headed)
    except Exception as e:
        print(f"❌ Failed to discover game URL from hub: {e}", file=sys.stderr)
        return 2

    # Step 2: requests-only scrape from the game URL
    try:
        payload, data_url = fetch_game_payload_from_game_url(game_url, timeout=args.timeout)
    except Exception as e:
        print(f"❌ Failed to fetch game payload: {e}", file=sys.stderr)
        return 3

    rows = iter_rows_from_payload(payload, source_url=data_url)

    added = append_new_rows(args.out, rows)

    print("✅ Done")
    print(f"Hub URL:       {args.hub_url}")
    print(f"Game URL:      {game_url}")
    print(f"Next data URL: {data_url}")
    print(f"Rows found:    {len(rows)}")
    print(f"Rows added:    {added}")
    print(f"CSV:           {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
