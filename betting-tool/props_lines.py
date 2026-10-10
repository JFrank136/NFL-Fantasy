#!/usr/bin/env python3
"""
Action Network player prop lines (pass/rush/receiving yards) across sportsbooks.

Each /nfl/props/<group> page embeds every book's over/under lines in its
__NEXT_DATA__ payload (initialMarketConfig.response.markets[book_id]), so plain
requests work -- no browser needed. Output: data/prop_lines.csv, one row per
(player, market, book, side).
"""
import csv
import json
import re
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
PAGES = {
    'passing-props': 'Pass Yds',
    'rushing': 'Rush Yds',
    'receiving': 'Rec Yds',
}
# Action Network book ids that aren't real sportsbooks
SKIP_BOOKS = {15, 30}  # Consensus, Open
OUT_FILE = 'data/prop_lines.csv'


def fetch_book_names():
    try:
        books = requests.get("https://api.actionnetwork.com/web/v1/books", headers=HEADERS, timeout=30).json()['books']
        # "DK NJ" / "Caesars NV" -> drop the trailing state so duplicates collapse
        return {b['id']: re.sub(r'\s+[A-Z]{2}$', '', b['display_name']) for b in books}
    except Exception:
        return {}


def fetch_page(slug):
    html = requests.get(f"https://www.actionnetwork.com/nfl/props/{slug}", headers=HEADERS, timeout=30).text
    m = re.search(r'__NEXT_DATA__[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"{slug}: no __NEXT_DATA__ found")
    cfg = json.loads(m.group(1))['props']['pageProps']['initialMarketConfig']
    return cfg['week'], cfg['response']


def parse(week, resp, stat, book_names):
    players = {p['id']: p for p in resp['players']}
    teams, games = {}, {}
    for g in resp['games']:
        games[g['id']] = g
        for side in ('home_team', 'away_team'):
            teams[g[side]['id']] = g[side]['abbr']
    rows = []
    for book_id, events in resp['markets'].items():
        book_id = int(book_id)
        if book_id in SKIP_BOOKS:
            continue
        for event_id, by_type in events.items():
            for lines in by_type.values():
                for ln in lines:
                    game = games.get(ln['event_id'])
                    if not game or game['status'] != 'scheduled' or ln.get('is_live') or ln.get('is_alt_market'):
                        continue
                    player = players.get(ln['player_id'])
                    if not player or ln.get('value') is None or ln.get('odds') is None:
                        continue
                    team = teams.get(player['team_id'])
                    opp = game['away_team']['abbr'] if team == game['home_team']['abbr'] else game['home_team']['abbr']
                    rows.append([week, player['full_name'], player['position'], team, opp, stat,
                                 book_names.get(book_id, str(book_id)), ln['side'], ln['value'], ln['odds'],
                                 game['start_time']])
    return rows


def main():
    book_names = fetch_book_names()
    all_rows = []
    for slug, stat in PAGES.items():
        print(f"Fetching {stat} lines... ", end='', flush=True)
        week, resp = fetch_page(slug)
        rows = parse(week, resp, stat, book_names)
        print(f"{len(rows)} lines (week {week})")
        all_rows.extend(rows)
    if not all_rows:
        raise SystemExit("No prop lines found (slate may not be posted yet).")
    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Week', 'Player', 'Pos', 'Team', 'Opp', 'Stat', 'Book', 'Side', 'Line', 'Odds', 'Start'])
        w.writerows(all_rows)
    print(f"Saved {len(all_rows)} lines to {OUT_FILE}")


if __name__ == "__main__":
    main()
