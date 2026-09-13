#!/usr/bin/env python3
"""
FFToday Fantasy Stats Scraper - Last 5 Weeks
Scrapes position vs defense stats similar to CBS scraper
"""

import requests
from bs4 import BeautifulSoup
import csv
import time
from pathlib import Path
from typing import List, Tuple

class FFTodayScraper:
    """Scraper for FFToday Fantasy Stats - Points Allowed by Position"""
    
    BASE_URL = "https://www.fftoday.com/stats/fantasystats.php"
    
    # Position IDs from FFToday
    POSITIONS = {
        'QB': '10',
        'RB': '20', 
        'WR': '30',
        'TE': '40'
    }
    
    # Configuration: (position, stat_name, column_index)
    # Column indices verified from actual FFToday tables:
    # QB: 0=Team, 1=G, 2=Cmp, 3=Att, 4=Yard(Pass), 5=TD, 6=INT, 7=Att(Rush), 8=Yard(Rush), 9=TD(Rush), 10=FPts, 11=FPts/G
    # RB/WR/TE: 0=Team, 1=G, 2=Att(Rush), 3=Yard(Rush), 4=TD(Rush), 5=Rec, 6=Yard(Rec), 7=TD(Rec), 8=FPts, 9=FPts/G
    SCRAPE_CONFIG = [
        ('QB', 'Pass Yards', 4),   # QB passing yards column (verified: Buccaneers=1,305)
        ('RB', 'Rush Yards', 3),   # RB rushing yards column (verified: Cardinals=712)
        ('RB', 'Rec', 5),          # RB receptions column (verified: Rams=28)
        ('RB', 'Rec Yards', 6),    # RB receiving yards column (verified: Eagles=257)
        ('WR', 'Rec', 5),          # WR receptions column (verified: Falcons=68)
        ('WR', 'Rec Yards', 6),    # WR receiving yards column (verified: Lions=959)
        ('TE', 'Rec', 5),          # TE receptions column (verified: Bengals=36)
        ('TE', 'Rec Yards', 6),    # TE receiving yards column (verified: Bengals=536)
    ]
    
    def __init__(self):
        """Initialize the scraper"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape_position_stats(self, position: str, col_idx: int) -> List[Tuple[str, float]]:
        """
        Scrape statistics for a specific position
        
        Args:
            position: Position code (QB, RB, WR, TE)
            col_idx: Column index for the stat to extract
        
        Returns:
            List of (team_name, stat_value) tuples
        """
        pos_id = self.POSITIONS.get(position)
        if not pos_id:
            print(f"  ✗ Unknown position: {position}")
            return []
        
        params = {
            'Season': '2025',
            'GameWeek': 'Last5',  # Last 5 weeks
            'PosID': pos_id,
            'Side': 'Allowed',
            'LeagueID': ''
        }
        
        print(f"Scraping {position}... ", end='', flush=True)
        
        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all tables and look for the one with team data
            # The stats table contains links with "vs. RB" pattern
            tables = soup.find_all('table')
            table = None
            for t in tables:
                # Check if this table has the team vs position pattern
                if t.find('a', string=lambda s: s and ' vs. ' in s):
                    table = t
                    break
            
            if not table:
                print(f"✗ No stats table found")
                return []
            
            # Find all data rows
            rows = table.find_all('tr')
            
            data = []
            for row in rows:
                cells = row.find_all('td')
                
                # Skip rows without enough cells
                # Format: Team, G, Att, Yard, TD, Rec, Yard, TD, FPts, FPts/G
                if len(cells) < 10:
                    continue
                
                # First cell contains team name with link
                team_link = cells[0].find('a')
                if not team_link:
                    continue
                
                team_text = team_link.get_text(strip=True)
                
                # Extract team name (format is "Cardinals vs. RB" or similar)
                if ' vs. ' in team_text:
                    team_name = team_text.split(' vs. ')[0]
                else:
                    continue
                
                # Get the stat value from the specified column
                try:
                    stat_text = cells[col_idx].get_text(strip=True)
                    stat_value = float(stat_text.replace(',', ''))
                    data.append((team_name, stat_value))
                except (ValueError, IndexError):
                    continue
            
            print(f"✓ Found {len(data)} teams")
            
            # Sort by stat value (descending = highest first)
            data.sort(key=lambda x: x[1], reverse=True)
            
            return data
            
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def scrape_all(self, output_file='data/last5_yds.csv'):
        """Scrape all configured stats and save to CSV"""
        print("="*60)
        print("FFTODAY FANTASY STATS SCRAPER - LAST 5 WEEKS")
        print("="*60)
        print()
        
        all_rows = []
        
        for position, stat_name, col_idx in self.SCRAPE_CONFIG:
            data = self.scrape_position_stats(position, col_idx)
            
            if data:
                # Add all teams with their values
                for team, value in data:
                    stat_category = f"{position} {stat_name}"
                    all_rows.append([stat_category, team, value, 'Last5 Yds'])
                
                # Show verification
                if len(data) >= 1:
                    print(f"  MOST: {data[0][0]} = {data[0][1]}")
                    if len(data) >= 2:
                        print(f"  LEAST: {data[-1][0]} = {data[-1][1]}")
            else:
                print(f"  ✗ Failed to get data")
            
            # Be polite to the server
            time.sleep(1)
        
        # Write to CSV
        if all_rows:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Stat_Category', 'Team', 'Value', 'Source'])
                writer.writerows(all_rows)
            
            print(f"\n{'='*60}")
            print(f"✓ SUCCESS! Data saved to: {output_file}")
            print(f"  Total rows: {len(all_rows)}")
            print(f"{'='*60}\n")
            
            print("Sample output (first 10 rows):")
            print("Stat_Category, Team, Value, Source")
            for row in all_rows[:10]:
                print(f"  {row[0]}, {row[1]}, {row[2]}, {row[3]}")
        else:
            print(f"\n✗ No data collected")

def main():
    scraper = FFTodayScraper()
    
    try:
        scraper.scrape_all('data/last5_yds.csv')
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()