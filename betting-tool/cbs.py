#!/usr/bin/env python3
"""
CBS Sports Fantasy Football Position vs Defense Scraper
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import csv
import random
from datetime import datetime
from pathlib import Path

class CBSSportsScraper:
    """Scraper for CBS Sports Fantasy Football Position vs Defense stats"""
    
    BASE_URL = "https://www.cbssports.com/fantasy/football/stats/posvsdef/{position}/ALL/avg/standard"
    
    # Configuration: (position, column_index, stat_name, label_suffix)
    SCRAPE_CONFIG = [
        ('QB', 4, 'Pass Yards', 'CBS Yds'),
        ('RB', 3, 'Rush Yards', 'CBS Yds'),
        ('RB', 7, 'Rec', 'CBS Yds'),
        ('RB', 8, 'Rec Yards', 'CBS Yds'),
        ('WR', 7, 'Rec', 'CBS Yds'),
        ('WR', 8, 'Rec Yards', 'CBS Yds'),
        ('TE', 7, 'Rec', 'CBS Yds'),
        ('TE', 8, 'Rec Yards', 'CBS Yds'),
    ]
    
    def __init__(self):
        """Initialize the scraper"""
        print("Initializing stealth browser...")
        options = uc.ChromeOptions()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--headless=new')
        
        self.driver = uc.Chrome(options=options, version_main=None)
        print("Browser initialized\n")
    
    def scrape_position_stats(self, position, stat_column_index):
        """Scrape statistics for a specific position"""
        url = self.BASE_URL.format(position=position)
        print(f"Scraping {position}... ", end='', flush=True)
        
        try:
            self.driver.get(url)
            time.sleep(random.uniform(4, 6))
            
            table = self.driver.find_element(By.CSS_SELECTOR, "table.data")
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
            
            # Skip header rows (first 3 rows) and extract data
            data = []
            for row in rows[3:]:  # Skip first 3 header rows
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) <= stat_column_index:
                        continue
                    
                    # Get team name from cell 1 and clean it
                    team_text = cells[1].text.strip()
                    team_name = team_text.replace(f"{position} vs ", "")
                    
                    # Get stat value
                    stat_value_text = cells[stat_column_index].text.strip()
                    
                    try:
                        stat_value = float(stat_value_text.replace(',', ''))
                    except ValueError:
                        continue
                    
                    if team_name and stat_value_text:
                        data.append((team_name, stat_value))
                        
                except Exception:
                    continue
            
            print(f"Found {len(data)} teams", end='')
            
            # IMPORTANT: Sort by the stat value (descending = highest first)
            data.sort(key=lambda x: x[1], reverse=True)
            
            if data:
                print(f" | Sorted by stat value")
            else:
                print()
            
            return data
            
        except Exception as e:
            print(f"âœ— Error: {e}")
            return []
    
    def format_output_rows(self, position, stat_name, label_suffix, data):
        """Format the scraped data into CSV rows with complete rankings"""
        rows = []
        
        if len(data) < 10:
            print(f"  ⚠ Warning: Only {len(data)} teams found")
        
        # Output all teams with their actual values
        for team, value in data:
            stat_category = f"{position} {stat_name}"
            rows.append([stat_category, team, value, label_suffix])
        
        return rows
    
    def scrape_all(self, output_file='data/cbs_yards.csv'):
        """Scrape all configured stats and save to CSV"""
        print("="*60)
        print("CBS SPORTS FANTASY FOOTBALL SCRAPER")
        print("="*60)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        all_rows = []
        
        for position, stat_col_idx, stat_name, label_suffix in self.SCRAPE_CONFIG:
            data = self.scrape_position_stats(position, stat_col_idx)
            
            if data:
                rows = self.format_output_rows(position, stat_name, label_suffix, data)
                all_rows.extend(rows)
                
                # Show verification
                if len(data) >= 5:
                    print(f"  MOST: {data[0][0]} = {data[0][1]}")
                    print(f"  LEAST: {data[-1][0]} = {data[-1][1]}")
            else:
                print(f"  âœ— Failed to get data")
            
            # Random delay between requests
            time.sleep(random.uniform(2, 4))
        
        # Write to CSV - create data directory if needed
        if all_rows:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Stat_Category', 'Team', 'Value', 'Source'])
                writer.writerows(all_rows)
            
            print(f"\n{'='*60}")
            print(f"SUCCESS! Data saved to: {output_file}")
            print(f"  Total rows: {len(all_rows)}")
            print(f"{'='*60}\n")
            
            print("Sample output (first 10 rows):")
            print("Stat_Category, Team, Value, Source")
            for row in all_rows[:10]:
                print(f"  {row[0]}, {row[1]}, {row[2]}, {row[3]}")
        else:
            print(f"\nâœ— No data collected")
        
        self.close()
    
    def close(self):
        """Clean up"""
        try:
            self.driver.quit()
            print("\nBrowser closed")
        except:
            pass

def main():
    scraper = CBSSportsScraper()
    
    try:
        scraper.scrape_all('data/cbs_yards.csv')
    except KeyboardInterrupt:
        print("\n\nâœ— Interrupted by user")
        scraper.close()
    except Exception as e:
        print(f"\nâœ— Error: {e}")
        scraper.close()

if __name__ == "__main__":
    main()