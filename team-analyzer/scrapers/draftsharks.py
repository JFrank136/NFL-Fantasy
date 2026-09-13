#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DraftSharks Complete Scraper & Formatter
1. Downloads ROS Rankings CSVs from DraftSharks
2. Moves/renames files to scrapers/data/draftsharks/
3. Formats and merges into draftsharks_week{X}.csv

URLs:
- https://www.draftsharks.com/ros-rankings/ppr
- https://www.draftsharks.com/ros-rankings/half-ppr

Week numbering: mirrors boone_trade.py approach (baseline Week 2, auto-increment every Tuesday)

Requires: 
  - DRAFTSHARKS_EMAIL and DRAFTSHARKS_PASSWORD in .env file
  - pip install selenium python-dotenv pandas

Usage:
  python scrapers/draftsharks.py
  
  To reset week:
  python scrapers/draftsharks.py --reset-week 5
"""

from __future__ import annotations
import os
import sys
import time
import random
import argparse
import shutil
import json
from pathlib import Path
from datetime import date, timedelta
from typing import Tuple, Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

load_dotenv()

# ---------- Config ----------
URLS = {
    "halfppr": "https://www.draftsharks.com/ros-rankings/half-ppr",
    "fullppr": "https://www.draftsharks.com/ros-rankings/ppr",
}

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = str(Path.home() / "Downloads")
DRAFTSHARKS_DATA_DIR = os.path.join(SCRIPT_DIR, "data", "draftsharks")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "data")
STATE_PATH = os.path.join(DRAFTSHARKS_DATA_DIR, "draftsharks_week_state.json")

os.makedirs(DRAFTSHARKS_DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Target positions
VALID_POSITIONS = ["QB", "RB", "WR", "TE"]

# ---------- Week numbering ----------
def most_recent_tuesday(today: date) -> date:
    return today - timedelta(days=(today.weekday() - 1) % 7)

def load_state() -> Optional[dict]:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def compute_week(today: date, reset_week: Optional[int] = None) -> Tuple[int, dict]:
    state = load_state() or {}
    
    if reset_week is not None:
        state["baseline_week"] = int(reset_week)
        state["baseline_tuesday"] = most_recent_tuesday(today).isoformat()
    
    if "baseline_week" not in state:
        state["baseline_week"] = 2
    if "baseline_tuesday" not in state:
        state["baseline_tuesday"] = most_recent_tuesday(today).isoformat()

    base_week = int(state["baseline_week"])
    base_tue = date.fromisoformat(state["baseline_tuesday"])
    weeks_since = max(0, (today - base_tue).days // 7)
    week = base_week + weeks_since
    return week, state

# ---------- Selenium setup ----------
def setup_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    opts.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=opts)
    driver.implicitly_wait(6)
    return driver

def _sleep(a=0.5, b=1.0):
    time.sleep(random.uniform(a, b))

# ---------- Login ----------
def try_login(driver: webdriver.Chrome) -> bool:
    """Login to DraftSharks using credentials from .env file."""
    email = os.getenv("DRAFTSHARKS_EMAIL")
    password = os.getenv("DRAFTSHARKS_PASSWORD")
    
    if not email or not password:
        print("❌ DRAFTSHARKS_EMAIL or DRAFTSHARKS_PASSWORD not found in .env file")
        return False

    try:
        driver.get("https://www.draftsharks.com/login")
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "form")))
        _sleep()

        # Email field
        email_el = None
        for sel in ["input[name='LoginForm[email]']", "#loginform-email", "input[type='email']"]:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            if found:
                email_el = found[0]
                break
        
        if not email_el:
            return False
        
        email_el.clear()
        email_el.send_keys(email)
        _sleep(0.3, 0.5)

        # Password field
        pwd_el = None
        for sel in ["input[name='LoginForm[password]']", "#loginform-password", "input[type='password']"]:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            if found:
                pwd_el = found[0]
                break
        
        if not pwd_el:
            return False
        
        pwd_el.clear()
        pwd_el.send_keys(password)
        _sleep(0.3, 0.5)

        # Submit
        btn = None
        for xp in [
            "//button[@type='submit']",
            "//button[contains(.,'Login') or contains(.,'LOG IN') or contains(.,'Sign In')]",
            "//input[@type='submit']",
        ]:
            found = driver.find_elements(By.XPATH, xp)
            if found:
                btn = found[0]
                break
        
        if btn:
            btn.click()
        else:
            pwd_el.submit()

        _sleep(1.5, 2.5)
        
        # Verify login
        pg = driver.page_source.lower()
        if any(k in pg for k in ["logout", "sign out", "my account", "dashboard"]):
            return True
            
    except Exception:
        return False
    
    return False

# ---------- Export CSV ----------
def click_export_button(driver: webdriver.Chrome, scoring_label: str):
    """Click export button and download CSV."""
    try:
        # Wait for page
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".menu-item.export-button"))
        )
        _sleep()
        
        # Open dropdown
        export_container_button = driver.find_element(By.CSS_SELECTOR, ".menu-item.export-button")
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", export_container_button)
        _sleep(0.3, 0.6)
        
        try:
            export_container_button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", export_container_button)
        
        _sleep(1.0, 1.5)
        
        # Find Export button (not Print button)
        buttons = driver.find_elements(By.CSS_SELECTOR, ".dropdown-container button.dropdown-item.btn")
        export_button = None
        for btn in buttons:
            btn_id = btn.get_attribute("id")
            if btn_id != "printPageButton":
                export_button = btn
                break
        
        if not export_button:
            raise TimeoutException("Could not find Export button")
        
        _sleep(0.3, 0.5)
        
        # Click export
        try:
            export_button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", export_button)
        
        _sleep(2.0, 3.0)
        
    except Exception as e:
        print(f"❌ Error exporting {scoring_label}: {e}")
        raise

# ---------- Scrape ----------
def scrape_ros_rankings(headless: bool = True):
    """Login and download both CSV files."""
    driver = setup_driver(headless=headless)
    
    try:
        if not try_login(driver):
            print("❌ Login failed")
            return False
        
        _sleep(1.0, 1.5)
        
        for scoring, url in URLS.items():
            driver.get(url)
            _sleep(1.0, 1.5)
            click_export_button(driver, scoring)
            _sleep(1.0, 1.5)
        
        return True
        
    except Exception as e:
        print(f"❌ Scraping error: {e}")
        return False
    finally:
        driver.quit()

# ---------- File operations ----------
def find_most_recent_file(directory: str, pattern: str) -> Optional[str]:
    """Find most recently modified file matching pattern."""
    files = list(Path(directory).glob(pattern))
    if not files:
        return None
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(files[0])

def move_and_rename_file(src_path: str, dest_dir: str, new_name: str) -> str:
    """Move and rename file."""
    dest_path = os.path.join(dest_dir, new_name)
    shutil.move(src_path, dest_path)
    return dest_path

# ---------- CSV Processing ----------
def process_csv(file_path: str, scoring_type: str) -> pd.DataFrame:
    """Extract Name, Pos, 3D Value for QB/RB/WR/TE."""
    df = pd.read_csv(file_path)
    
    # Find columns
    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if 'player' in col_lower and 'name' not in col_lower:
            col_map['name'] = col
        elif 'fantasy position' in col_lower or col_lower in ['pos', 'position']:
            col_map['pos'] = col
        elif '3d value' in col_lower or '3d-value' in col_lower:
            col_map['value'] = col
    
    if 'name' not in col_map or 'pos' not in col_map or 'value' not in col_map:
        raise ValueError(f"Missing columns in {file_path}")
    
    # Extract
    result = pd.DataFrame({
        'Name': df[col_map['name']],
        'Pos': df[col_map['pos']],
        scoring_type: df[col_map['value']]
    })
    
    # Filter positions
    result['Pos'] = result['Pos'].str.upper().str.strip()
    result = result[result['Pos'].isin(VALID_POSITIONS)].copy()
    result['Name'] = result['Name'].str.strip()
    result[scoring_type] = pd.to_numeric(result[scoring_type], errors='coerce').fillna(0).astype(int)
    
    return result

def merge_dataframes(half_df: pd.DataFrame, full_df: pd.DataFrame) -> pd.DataFrame:
    """Merge half-ppr and full-ppr data."""
    merged = pd.merge(
        half_df[['Name', 'Pos', 'half_ppr']],
        full_df[['Name', 'Pos', 'full_ppr']],
        on=['Name', 'Pos'],
        how='outer'
    )
    
    merged['half_ppr'] = merged['half_ppr'].fillna(0).astype(int)
    merged['full_ppr'] = merged['full_ppr'].fillna(0).astype(int)
    
    # Sort by Position then full_ppr
    pos_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
    merged['__pos_order__'] = merged['Pos'].map(lambda x: pos_order.get(x, 9))
    merged = merged.sort_values(['__pos_order__', 'full_ppr'], ascending=[True, False])
    merged = merged.drop(columns='__pos_order__').reset_index(drop=True)
    
    return merged[['Name', 'Pos', 'half_ppr', 'full_ppr']]

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-week", type=int, default=None, 
                       help="Reset baseline week (e.g., --reset-week 5)")
    args = parser.parse_args()
    
    today = date.today()
    week, new_state = compute_week(today, reset_week=args.reset_week)
    save_state(new_state)
    
    print(f"\n{'='*60}")
    print(f"DraftSharks Scraper & Formatter - Week {week}")
    print(f"{'='*60}\n")
    
    # Step 1: Scrape
    print("Step 1: Downloading CSVs from DraftSharks...")
    if not scrape_ros_rankings(headless=False):
        print("❌ Download failed")
        return
    print("✅ Download complete\n")
    
    # Step 2: Find files
    print("Step 2: Locating downloaded files...")
    half_ppr_src = find_most_recent_file(DOWNLOADS_DIR, "ros-rankings-half-ppr.csv")
    full_ppr_src = find_most_recent_file(DOWNLOADS_DIR, "ros-rankings-ppr.csv")
    
    if not half_ppr_src or not full_ppr_src:
        print("❌ Could not find downloaded files")
        return
    print("✅ Files found\n")
    
    # Step 3: Move and rename
    print("Step 3: Moving and renaming files...")
    half_ppr_dest = move_and_rename_file(
        half_ppr_src,
        DRAFTSHARKS_DATA_DIR,
        f"draftsharks_halfppr_{week}.csv"
    )
    full_ppr_dest = move_and_rename_file(
        full_ppr_src,
        DRAFTSHARKS_DATA_DIR,
        f"draftsharks_fullppr_{week}.csv"
    )
    print("✅ Files moved\n")
    
    # Step 4: Process and merge
    print("Step 4: Processing and merging data...")
    half_df = process_csv(half_ppr_dest, 'half_ppr')
    full_df = process_csv(full_ppr_dest, 'full_ppr')
    merged_df = merge_dataframes(half_df, full_df)
    print("✅ Data processed\n")
    
    # Step 5: Save
    output_path = os.path.join(OUTPUT_DIR, f"draftsharks_week{week}.csv")
    merged_df.to_csv(output_path, index=False)
    
    print(f"{'='*60}")
    print(f"✅ SUCCESS")
    print(f"{'='*60}")
    print(f"Output: {os.path.basename(output_path)}")
    print(f"Players: {len(merged_df)} (QB/RB/WR/TE only)")
    print(f"Location: {OUTPUT_DIR}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()