#!/usr/bin/env python3
"""
Draft Sharks per-stat weekly projections (pass/rush/rec yards, receptions).

Same public weekly-rankings/load-rows endpoint the in-season pipeline uses, but
with researchDepth=projections, which returns stat-line cells instead of fantasy
points. Week comes from BETTING_WEEK, else from data/prop_lines.csv.
Output: data/ds_projections.csv
"""
import csv
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://www.draftsharks.com/weekly-rankings/load-rows"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
STATS = ['pass_yds', 'rush_yds', 'rec_yds', 'rec_catch']
OUT_FILE = 'data/ds_projections.csv'


def get_week():
    if os.environ.get('BETTING_WEEK'):
        return int(os.environ['BETTING_WEEK'])
    with open('data/prop_lines.csv', encoding='utf-8') as f:
        return int(next(csv.DictReader(f))['Week'])


def fetch(week):
    rows, offset = [], 0
    while True:
        r = requests.get(URL, headers=HEADERS, timeout=30, params=dict(
            offset=offset, limit=300, fantasyPosition="", pprSuperflexSlug="ppr",
            sort="-weekly3dPts", week=week, researchDepth="projections"))
        r.raise_for_status()
        bodies = BeautifulSoup(r.text, "html.parser").select("tbody[data-player-row]")
        if not bodies:
            return rows
        for tb in bodies:
            pos = tb.get("data-fantasy-position", "")
            if pos not in ('QB', 'RB', 'WR', 'TE'):
                continue
            cells = {td["data-attribute"]: td.get("data-value") for td in tb.select("td[data-attribute]")}
            img = tb.select_one("img.team-badge")
            m = re.search(r"/teams/([A-Z]+)\.svg", img["src"]) if img and img.get("src") else None
            vals = []
            for s in STATS:
                try:
                    vals.append(float(cells.get(s) or 0))
                except ValueError:
                    vals.append(0.0)
            rows.append([week, tb.get("data-player-name", "").strip(), pos, m.group(1) if m else ''] + vals)
        offset += len(bodies)


def main():
    week = get_week()
    print(f"Fetching Draft Sharks stat projections (week {week})... ", end='', flush=True)
    rows = fetch(week)
    if not rows:
        raise SystemExit("No projections returned.")
    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Week', 'Player', 'Pos', 'Team'] + STATS)
        w.writerows(rows)
    print(f"{len(rows)} players -> {OUT_FILE}")


if __name__ == "__main__":
    main()
