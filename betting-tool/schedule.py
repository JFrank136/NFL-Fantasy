import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import pytz
import time

def get_nfl_schedule_api(season=2025, season_type=2):
    """
    Scrape NFL schedule from ESPN API (preferred method)
    
    Parameters:
    - season: int, year (default 2025)
    - season_type: int, 1=Preseason, 2=Regular Season, 3=Playoffs (default 2)
    
    Returns:
    - DataFrame with schedule data
    """
    
    schedule_data = []
    
    # Regular season has 18 weeks
    weeks = 18 if season_type == 2 else 4
    
    # Headers to avoid 403 errors
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.espn.com/'
    }
    
    for week in range(1, weeks + 1):
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype={season_type}&week={week}&dates={season}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Parse each game in the week
            if 'events' in data:
                for event in data['events']:
                    game_info = parse_game_from_api(event, week)
                    if game_info:
                        schedule_data.append(game_info)
                        
            print(f"✓ Scraped Week {week}")
            time.sleep(0.5)  # Be polite to the server
            
        except Exception as e:
            print(f"✗ Error scraping Week {week}: {str(e)}")
            continue
    
    if not schedule_data:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(schedule_data)
    
    # Reorder columns
    column_order = ['week', 'game_date_est', 'game_time_est', 'day_of_week', 
                    'away_team', 'home_team', 'is_dome', 'weather']
    df = df[column_order]
    
    return df


def get_nfl_schedule_html(season=2025, season_type=2):
    """
    Scrape NFL schedule from ESPN HTML pages (backup method)
    
    Parameters:
    - season: int, year (default 2025)
    - season_type: int, 1=Preseason, 2=Regular Season, 3=Playoffs (default 2)
    
    Returns:
    - DataFrame with schedule data
    """
    
    schedule_data = []
    
    # Regular season has 18 weeks
    weeks = 18 if season_type == 2 else 4
    
    # Headers to avoid blocking
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for week in range(1, weeks + 1):
        url = f"https://www.espn.com/nfl/schedule/_/week/{week}/year/{season}/seasontype/{season_type}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all game rows
            games = soup.find_all('tbody', class_='Table__TBODY')
            
            for game_table in games:
                rows = game_table.find_all('tr', class_='Table__TR')
                
                for row in rows:
                    game_info = parse_game_from_html(row, week, season)
                    if game_info:
                        schedule_data.append(game_info)
                        
            print(f"✓ Scraped Week {week}")
            time.sleep(1)  # Be polite to the server
            
        except Exception as e:
            print(f"✗ Error scraping Week {week}: {str(e)}")
            continue
    
    if not schedule_data:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(schedule_data)
    
    # Reorder columns
    column_order = ['week', 'game_date_est', 'game_time_est', 'day_of_week', 
                    'away_team', 'home_team', 'is_dome', 'weather']
    
    # Add missing columns if they don't exist
    for col in column_order:
        if col not in df.columns:
            df[col] = None
            
    df = df[column_order]
    
    return df


def parse_game_from_api(event, week):
    """Parse individual game data from ESPN API response"""
    
    try:
        competition = event['competitions'][0]
        
        # Get teams
        home_team = None
        away_team = None
        
        for competitor in competition['competitors']:
            team_name = competitor['team']['displayName']
            if competitor['homeAway'] == 'home':
                home_team = team_name
            else:
                away_team = team_name
        
        # Get date/time in EST
        game_datetime_utc = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        est = pytz.timezone('US/Eastern')
        game_datetime_est = game_datetime_utc.astimezone(est)
        
        game_date = game_datetime_est.strftime('%Y-%m-%d')
        game_time = game_datetime_est.strftime('%I:%M %p')
        day_of_week = game_datetime_est.strftime('%A')
        
        # Get venue info (dome status)
        is_dome = None
        if 'venue' in competition:
            is_dome = competition['venue'].get('indoor', None)
        
        # Get weather (if available)
        weather = None
        if 'weather' in event:
            temp = event['weather'].get('temperature', '')
            condition = event['weather'].get('displayValue', '')
            if temp and condition:
                weather = f"{temp}°F, {condition}"
            elif condition:
                weather = condition
        
        return {
            'week': week,
            'game_date_est': game_date,
            'game_time_est': game_time,
            'day_of_week': day_of_week,
            'away_team': away_team,
            'home_team': home_team,
            'is_dome': is_dome,
            'weather': weather
        }
        
    except Exception as e:
        print(f"Error parsing game from API: {str(e)}")
        return None


def parse_game_from_html(row, week, season):
    """Parse individual game data from ESPN HTML"""
    
    try:
        # Get teams
        team_cells = row.find_all('span', class_='Table__Team')
        if len(team_cells) < 2:
            return None
            
        away_team = team_cells[0].get_text(strip=True) if len(team_cells) > 0 else None
        home_team = team_cells[1].get_text(strip=True) if len(team_cells) > 1 else None
        
        # Get time
        time_cell = row.find('td', class_='date__col')
        game_time = None
        game_date = None
        day_of_week = None
        
        if time_cell:
            time_link = time_cell.find('a')
            if time_link:
                game_time = time_link.get_text(strip=True)
        
        # Get location (for dome info - would need additional lookup)
        location_cell = row.find('td', class_='location__col')
        location = None
        if location_cell:
            location = location_cell.get_text(strip=True)
        
        # Determine if dome (simplified - would need stadium database)
        is_dome = None
        if location:
            dome_stadiums = ['Mercedes-Benz Stadium', 'AT&T Stadium', 'Allegiant Stadium', 
                           'SoFi Stadium', 'U.S. Bank Stadium', 'Ford Field', 
                           'Lucas Oil Stadium', 'Caesars Superdome']
            is_dome = any(stadium in location for stadium in dome_stadiums)
        
        return {
            'week': week,
            'game_date_est': game_date,
            'game_time_est': game_time,
            'day_of_week': day_of_week,
            'away_team': away_team,
            'home_team': home_team,
            'is_dome': is_dome,
            'weather': None
        }
        
    except Exception as e:
        print(f"Error parsing game from HTML: {str(e)}")
        return None


if __name__ == "__main__":
    # Scrape 2025 regular season schedule
    print("Scraping 2025 NFL Regular Season Schedule...")
    print("=" * 60)
    
    # Try API method first
    print("\nAttempting API method...\n")
    schedule_df = get_nfl_schedule_api(season=2025, season_type=2)
    
    # If API fails, try HTML scraping
    if schedule_df.empty:
        print("\n⚠ API method failed. Trying HTML scraping method...\n")
        schedule_df = get_nfl_schedule_html(season=2025, season_type=2)
    
    if schedule_df.empty:
        print("\n❌ Both methods failed. No data to save.")
        print("\nPossible solutions:")
        print("1. Run this script from your local machine (not a server)")
        print("2. Use a VPN or different network")
        print("3. Wait and try again later")
    else:
        # Save to CSV
        output_file = 'nfl_schedule_2025.csv'
        schedule_df.to_csv(output_file, index=False)
        
        print(f"\n✓ Schedule saved to {output_file}")
        print(f"✓ Total games: {len(schedule_df)}")
        
        # Display first few games
        print("\nFirst 10 games:")
        print(schedule_df.head(10).to_string(index=False))
        
        # Display summary
        if len(schedule_df) > 0:
            print(f"\n{'=' * 60}")
            print("SUMMARY")
            print(f"{'=' * 60}")
            print(f"Weeks: {schedule_df['week'].min()} - {schedule_df['week'].max()}")
            if schedule_df['game_date_est'].notna().any():
                print(f"Date range: {schedule_df['game_date_est'].min()} to {schedule_df['game_date_est'].max()}")
            if schedule_df['is_dome'].notna().any():
                print(f"Dome games: {schedule_df['is_dome'].sum()} / {len(schedule_df)}")