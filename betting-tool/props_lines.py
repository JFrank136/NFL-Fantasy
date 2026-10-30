#!/usr/bin/env python3
"""
Action Network player prop lines (pass/rush/receiving yards, receptions) across sportsbooks.

Uses the same JSON endpoint the site's props tables call (/web/v2/scoreboard/nfl/markets),
so plain requests work -- no browser needed. The bookIds param picks the sportsbooks. Output: data/prop_lines.csv, one row per
(player, market, book, side).
"""
import csv
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
# Action Network book ids we care about (one state variant each; lines match across states)
BOOKS = {68: 'DraftKings', 69: 'FanDuel', 75: 'BetMGM', 123: 'Caesars', 2400: 'Fanatics', 2127: 'Hard Rock'}
MARKETS = {
    'core_bet_type_9_passing_yards': 'Pass Yds',
    'core_bet_type_12_rushing_yards': 'Rush Yds',
    'core_bet_type_16_receiving_yards': 'Rec Yds',
    'core_bet_type_15_receptions': 'Receptions',
}
API = "https://api.actionnetwork.com/web/v2/scoreboard/nfl/markets"
OUT_FILE = 'data/prop_lines.csv'
COLUMNS = ['Week', 'Player', 'Pos', 'Team', 'Opp', 'Stat', 'Book', 'Side', 'Line', 'Odds', 'Start', 'GameId', 'PlayerId']


def fetch_markets():
    params = {'bookIds': ','.join(map(str, BOOKS)), 'customPickTypes': ','.join(MARKETS), 'periods': 'event'}
    r = requests.get(API, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def parse(resp):
    players = {p['id']: p for p in resp['players']}
    teams, games = {}, {}
    for g in resp['games']:
        games[g['id']] = g
        for side in ('home_team', 'away_team'):
            teams[g[side]['id']] = g[side]['abbr']
    rows = []
    for book_id, events in resp['markets'].items():
        if int(book_id) not in BOOKS:
            continue
        for by_type in events.values():
            for market, lines in by_type.items():
                stat = MARKETS.get(market)
                if not stat:
                    continue
                for ln in lines:
                    game = games.get(ln['event_id'])
                    if not game or game['status'] != 'scheduled' or ln.get('is_live') or ln.get('is_alt_market'):
                        continue
                    player = players.get(ln['player_id'])
                    if not player or ln.get('value') is None or ln.get('odds') is None:
                        continue
                    team = teams.get(player['team_id'])
                    opp = game['away_team']['abbr'] if team == game['home_team']['abbr'] else game['home_team']['abbr']
                    rows.append([game['week'], player['full_name'], player['position'], team, opp, stat,
                                 BOOKS[int(book_id)], ln['side'], ln['value'], ln['odds'], game['start_time'],
                                 ln['event_id'], ln['player_id']])
    return rows


def main():
    print("Fetching Pass/Rush/Rec Yds and Receptions lines... ", end='', flush=True)
    all_rows = parse(fetch_markets())
    if not all_rows:
        raise SystemExit("No prop lines found (slate may not be posted yet).")
    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(all_rows)
    books = sorted({r[6] for r in all_rows})
    print(f"{len(all_rows)} lines from {', '.join(books)} -> {OUT_FILE}")


if __name__ == "__main__":
    main()
