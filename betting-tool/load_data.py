#!/usr/bin/env python3
"""
Data loader for BetHub - loads CSV files into the database
"""

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path("bethub.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def load_roster(csv_path: str, week: int = 1):
    """Load roster CSV into database"""
    print(f"Loading roster from {csv_path}...")
    
    roster = pd.read_csv(csv_path)
    roster["week_loaded"] = week
    
    # Ensure required columns exist
    required = ["player", "team", "position"]
    missing = [col for col in required if col not in roster.columns]
    if missing:
        print(f"  ⚠ Missing columns: {missing}")
        return
    
    # Only keep columns that exist in the database
    valid_cols = ["player", "team", "position", "depth", "week_loaded"]
    roster = roster[[col for col in valid_cols if col in roster.columns]]
    
    with get_conn() as con:
        roster.to_sql("roster", con, if_exists="append", index=False)
    
    print(f"  ✓ Loaded {len(roster)} roster entries")

def load_schedule(csv_path: str):
    """Load schedule CSV into database"""
    print(f"Loading schedule from {csv_path}...")
    
    schedule = pd.read_csv(csv_path)
    
    # Map column names if needed
    # Expected: game_id, week, home, away, kickoff_utc
    col_map = {
        'game_date_est': 'kickoff_utc',
        'away_team': 'away',
        'home_team': 'home',
    }
    
    schedule = schedule.rename(columns=col_map)
    
    # Create game_id if not present
    if 'game_id' not in schedule.columns:
        schedule['game_id'] = schedule.apply(
            lambda r: f"w{r.get('week', 0)}_{r.get('away', '')}_{r.get('home', '')}".replace(' ', '_'),
            axis=1
        )
    
    # Select only needed columns
    cols_to_keep = ['game_id', 'week', 'home', 'away', 'kickoff_utc']
    schedule = schedule[[col for col in cols_to_keep if col in schedule.columns]]
    
    with get_conn() as con:
        schedule.to_sql("schedule", con, if_exists="append", index=False)
    
    print(f"  ✓ Loaded {len(schedule)} schedule entries")

def load_picks(csv_path: str):
    """Load picks CSV into database"""
    print(f"Loading picks from {csv_path}...")
    
    picks = pd.read_csv(csv_path)
    
    # Map column names if needed
    col_map = {
        'Bet': 'pick_text',
        'Team': 'team',
        'Source': 'source',
        'Player': 'player',
    }
    
    picks = picks.rename(columns=col_map)
    
    # Add missing columns with defaults
    if 'week' not in picks.columns:
        picks['week'] = 1
    if 'like' not in picks.columns:
        picks['like'] = 0
    if 'love' not in picks.columns:
        picks['love'] = 0
    if 'notes' not in picks.columns:
        picks['notes'] = None
    
    # Clean up empty strings to None for optional fields
    for col in ['team', 'player', 'notes', 'game_id']:
        if col in picks.columns:
            picks[col] = picks[col].replace('', None)
    
    # Select only needed columns
    cols_to_keep = ['week', 'game_id', 'team', 'player', 'pick_text', 'source', 'like', 'love', 'notes']
    picks = picks[[col for col in cols_to_keep if col in picks.columns]]
    
    with get_conn() as con:
        picks.to_sql("picks", con, if_exists="append", index=False)
    
    print(f"  ✓ Loaded {len(picks)} picks")

def main():
    print("=" * 60)
    print("BetHub Data Loader")
    print("=" * 60)
    
    # Check which files exist in data/ folder
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    files = {
        'roster': data_dir / 'roster_latest.csv',
        'schedule': data_dir / 'nfl_schedule_2025.csv',
        'picks_betting': data_dir / 'betting_info.csv',
        'picks_cbs': data_dir / 'cbs_fantasy_stats.csv',
    }
    
    print("\nLooking for CSV files in data/ folder...")
    for name, path in files.items():
        if path.exists():
            print(f"  ✓ Found {path}")
        else:
            print(f"  ✗ Missing {path}")
    
    print("\n" + "=" * 60)
    
    # Load roster
    if files['roster'].exists():
        load_roster(str(files['roster']), week=1)
    
    # Load schedule
    if files['schedule'].exists():
        load_schedule(str(files['schedule']))
    
    # Load picks from betting_info
    if files['picks_betting'].exists():
        load_picks(str(files['picks_betting']))
    
    # Load picks from cbs_fantasy_stats
    if files['picks_cbs'].exists():
        load_picks(str(files['picks_cbs']))
    
    print("\n" + "=" * 60)
    print("✓ Data loading complete!")
    print("=" * 60)
    
    # Show summary
    with get_conn() as con:
        roster_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM roster", con)['cnt'][0]
        schedule_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM schedule", con)['cnt'][0]
        picks_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM picks", con)['cnt'][0]
    
    print("\nDatabase Summary:")
    print(f"  Roster entries: {roster_count}")
    print(f"  Schedule games: {schedule_count}")
    print(f"  Picks: {picks_count}")

if __name__ == "__main__":
    main()