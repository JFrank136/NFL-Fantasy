#!/usr/bin/env python3
"""
NFL Depth Chart Scraper - Focused on key fantasy positions
Scrapes from ESPN roster pages with position filtering
"""

import csv
import time
import re
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

# ESPN team slugs (CORRECTED)
ESPN_TEAMS = {
    "ARI": "ari", "ATL": "atl", "BAL": "bal", "BUF": "buf",
    "CAR": "car", "CHI": "chi", "CIN": "cin", "CLE": "cle",
    "DAL": "dal", "DEN": "den", "DET": "det", "GB": "gb",
    "HOU": "hou", "IND": "ind", "JAX": "jax", "KC": "kc",
    "LAC": "lac", "LAR": "lar", "LV": "lv", "MIA": "mia",
    "MIN": "min", "NE": "ne", "NO": "no", "NYG": "nyg",
    "NYJ": "nyj", "PHI": "phi", "PIT": "pit", "SEA": "sea",
    "SF": "sf", "TB": "tb", "TEN": "ten", "WSH": "wsh"
}

# Positions to scrape (no limits - get all players at these positions)
TARGET_POSITIONS = {"QB", "RB", "WR", "TE"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_player_name(name: str) -> str:
    """Clean player name by removing injury designations, jersey numbers, and extra whitespace"""
    # Remove injury codes like (Q), (D), (IR), etc.
    name = re.sub(r'\s*\([A-Z]+\)\s*', '', name)
    # Remove jersey numbers at the end
    name = re.sub(r'\d+$', '', name)
    # Remove extra whitespace
    name = ' '.join(name.split())
    return name.strip()


def fetch_roster(team_abbr: str) -> List[Dict[str, str]]:
    """Fetch roster for a specific team from ESPN"""
    
    team_slug = ESPN_TEAMS.get(team_abbr)
    if not team_slug:
        print(f"  ⚠ Unknown team: {team_abbr}")
        return []
    
    url = f"https://www.espn.com/nfl/team/roster/_/name/{team_slug}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ HTTP error for {team_abbr}: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    
    # ESPN roster tables are in ResponsiveTable divs
    tables = soup.find_all("div", class_="ResponsiveTable")
    
    for table in tables:
        # Find all rows in the table
        table_rows = table.find_all("tr", class_=re.compile(r"Table__TR"))
        
        for row in table_rows:
            try:
                cells = row.find_all(["td", "th"])
                
                if len(cells) < 3:
                    continue
                
                # Cell 0: Headshot
                # Cell 1: Player Name (contains <a> link)
                # Cell 2: Position
                
                # Get player name from cell 1
                name_cell = cells[1]
                player_link = name_cell.find("a", class_="AnchorLink")
                
                if not player_link:
                    continue
                
                # Extract text from the link tag itself
                player_name = player_link.get_text(strip=True)
                
                # Also check if the full cell text has more (like jersey number)
                # but we only want the name part
                full_cell_text = name_cell.get_text(strip=True)
                
                # If the link text is empty but cell has text, extract name before number
                if not player_name and full_cell_text:
                    # Name is usually everything except trailing numbers
                    player_name = re.sub(r'\d+$', '', full_cell_text).strip()
                
                player_name = clean_player_name(player_name)
                
                if not player_name or len(player_name) < 3:
                    continue
                
                # Get position from cell 2
                position_cell = cells[2]
                position = position_cell.get_text(strip=True).upper()
                
                # Validate position - handle "WR" appearing multiple times
                # Extract just the position abbreviation (QB, RB, WR, TE, etc.)
                position_match = re.match(r'^(QB|RB|WR|TE|FB)', position)
                if not position_match:
                    continue
                
                position = position_match.group(1)
                
                # Skip FB if not in our target positions
                if position not in TARGET_POSITIONS:
                    continue
                
                rows.append({
                    "player": player_name,
                    "team": team_abbr,
                    "position": position
                })
                
            except Exception:
                continue
    
    # Assign depth based on order (ESPN lists starters first)
    position_counts = {pos: 0 for pos in TARGET_POSITIONS}
    final_rows = []
    
    for row in rows:
        pos = row["position"]
        position_counts[pos] += 1
        row["depth"] = position_counts[pos]
        final_rows.append(row)
    
    return final_rows


def scrape_all(output_csv: Path):
    """Scrape rosters for all NFL teams"""
    
    print("=" * 60)
    print("NFL DEPTH CHART SCRAPER (ESPN Rosters)")
    print("=" * 60)
    print(f"Positions: {', '.join(sorted(TARGET_POSITIONS))}")
    print("Scraping ALL players at these positions")
    print("=" * 60)
    print()
    
    all_rows = []
    successful_teams = 0
    failed_teams = []
    total_teams = len(ESPN_TEAMS)
    
    for idx, team_abbr in enumerate(sorted(ESPN_TEAMS.keys()), 1):
        try:
            rows = fetch_roster(team_abbr)
            
            if rows:
                all_rows.extend(rows)
                successful_teams += 1
            else:
                failed_teams.append(team_abbr)
            
            # Show progress every 5 teams or at the end
            if idx % 5 == 0 or idx == total_teams:
                progress_pct = (idx / total_teams) * 100
                print(f"Progress: {idx}/{total_teams} ({progress_pct:.0f}%) - {len(all_rows)} players scraped")
            
            # Be respectful with rate limiting
            time.sleep(0.8)
            
        except Exception as e:
            failed_teams.append(team_abbr)
    
    # Write results
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["player", "team", "position", "depth"])
        writer.writeheader()
        writer.writerows(all_rows)
    
    print()
    print("=" * 60)
    print(f"✓ Complete!")
    print(f"  Teams processed: {successful_teams}/{len(ESPN_TEAMS)}")
    if failed_teams:
        print(f"  Failed teams: {', '.join(failed_teams)}")
    print(f"  Total players: {len(all_rows)}")
    print(f"  Output: {output_csv}")
    print("=" * 60)
    
    # Show summary by position
    print("\nPosition Summary:")
    for pos in sorted(TARGET_POSITIONS):
        count = len([r for r in all_rows if r["position"] == pos])
        print(f"  {pos}: {count} players")


if __name__ == "__main__":
    scrape_all(Path("data/roster_latest.csv"))