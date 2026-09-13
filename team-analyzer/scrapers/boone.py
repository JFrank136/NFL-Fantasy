#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Boone Trade Value Charts -> data/boone_week{X}.csv
Columns: PosRank, Name, Position, half_ppr, full_ppr

- Uses Selenium to scrape HTML tables (Yahoo no longer uses Datawrapper iframes)
- Auto-discovers latest article URLs from Justin Boone's author page
- RB/WR/TE: Half PPR + Full PPR
- QB: use 1QB column and copy into both half_ppr and full_ppr
- Week numbering: baseline Week 2; auto-increments every Tuesday
- Validates against previous week (95% similarity threshold)

Usage:
  pip install selenium pandas
  python boone.py
"""

import argparse
import json
import os
import re
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---- Config ----
AUTHOR_PAGE = "https://sports.yahoo.com/author/justin-boone/"
DATA_DIR = os.path.join(os.getcwd(), "data")
STATE_PATH = os.path.join(DATA_DIR, "boone_week_state.json")
os.makedirs(DATA_DIR, exist_ok=True)

# ---- Week numbering ----

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

def compute_week(today: date, reset_week: Optional[int], baseline_tuesday: Optional[str]) -> Tuple[int, dict]:
    state = load_state() or {}
    if reset_week is not None:
        state["baseline_week"] = int(reset_week)
    if baseline_tuesday is not None:
        state["baseline_tuesday"] = baseline_tuesday

    if "baseline_week" not in state:
        state["baseline_week"] = 2
    if "baseline_tuesday" not in state:
        state["baseline_tuesday"] = most_recent_tuesday(today).isoformat()

    base_week = int(state["baseline_week"])
    base_tue = date.fromisoformat(state["baseline_tuesday"])
    weeks_since = max(0, (today - base_tue).days // 7)
    week = base_week + weeks_since
    return week, state

# ---- Auto-discovery ----

def discover_trade_value_urls(expected_week: int, driver: webdriver.Chrome) -> Optional[Dict[str, str]]:
    """
    Discover the latest Trade Value Chart URLs from Justin Boone's author page.
    Returns dict of position->URL if all 4 positions found for the expected week, else None.
    """
    print(f"[*] Discovering URLs for Week {expected_week}...", end=" ", flush=True)
    
    try:
        driver.set_page_load_timeout(30)
        driver.get(AUTHOR_PAGE)
        time.sleep(5)
        
        # Click Articles tab
        try:
            label = driver.find_element(By.XPATH, "//label[contains(text(), 'Articles')]")
            label.click()
            time.sleep(3)
        except:
            pass
        
        # Wait for content to load (no scrolling to avoid timeouts)
        time.sleep(2)
        
        # Find all article links (only fantasy articles)
        article_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/fantasy/article/')]")
        
        position_keywords = {
            "QB": ["quarterback"],
            "RB": ["running back", "running-back"],
            "WR": ["wide receiver", "wide-receiver"],
            "TE": ["tight end", "tight-end"],
        }
        
        found_urls = {}
        
        for link in article_links:
            try:
                # Try to get text - first from link, then from parent element
                text = link.text.strip() if link.text else ""
                
                if not text:
                    try:
                        parent = link.find_element(By.XPATH, "..")
                        text = parent.text.strip() if parent.text else ""
                    except:
                        pass
                
                if not text:
                    continue
                
                text = text.lower()
                href = link.get_attribute('href')
                
                if not href:
                    continue
                
                if "trade value" not in text and "rest of season" not in text:
                    continue
                
                if "for week" not in text:
                    continue
                
                week_match = re.search(r'week\s+(\d+)', text)
                if not week_match:
                    continue
                
                article_week = int(week_match.group(1))
                
                if article_week != expected_week:
                    continue
                
                for pos, keywords in position_keywords.items():
                    if pos in found_urls:
                        continue
                    
                    for keyword in keywords:
                        if keyword in text:
                            found_urls[pos] = href
                            break
            except:
                pass
        
        if len(found_urls) == 4:
            print(f"[OK] Found all 4 positions")
            return found_urls
        else:
            missing = set(["QB", "RB", "WR", "TE"]) - set(found_urls.keys())
            print(f"[X] Missing: {missing}")
            return None
            
    except Exception as e:
        print(f"[X] Failed: {e}")
        return None

# ---- Scraping ----

def scrape_position_table(url: str, position: str, driver: webdriver.Chrome) -> pd.DataFrame:
    """
    Scrape the HTML table from a position's article page.
    Returns DataFrame with columns: PosRank, Name, Position, half_ppr, full_ppr
    """
    print(f"[{position}] Scraping...", end=" ", flush=True)
    
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(3)
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)
        
        tables = driver.find_elements(By.TAG_NAME, 'table')
        
        if not tables:
            print(f"[X] No tables found")
            return pd.DataFrame()
        
        table = tables[0]
        
        header_cells = table.find_elements(By.XPATH, ".//thead//th | .//thead//td | .//tr[1]//th | .//tr[1]//td")
        headers = [cell.text.strip() for cell in header_cells]
        
        rows = table.find_elements(By.XPATH, ".//tbody//tr | .//tr[position()>1]")
        
        data = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, 'td')
            if not cells:
                cells = row.find_elements(By.TAG_NAME, 'th')
            
            if cells:
                row_data = [cell.text.strip() for cell in cells]
                data.append(row_data)
        
        if not data:
            print(f"[X] No data rows found")
            return pd.DataFrame()
        
        print(f"[OK] {len(data)} players")
        
        df = pd.DataFrame(data, columns=headers[:len(data[0])])
        df.columns = [col.lower().strip() for col in df.columns]
        
        result = []
        for idx, row in df.iterrows():
            name = None
            for col in ['player', 'name']:
                if col in df.columns:
                    name = row[col]
                    break
            
            if not name or pd.isna(name):
                continue
            
            rank = None
            for col in ['rk', 'rank', 'rnk']:
                if col in df.columns:
                    rank = row[col]
                    break
            
            half_val = None
            full_val = None
            
            if position == "QB":
                for col in ['1qb', '1 qb']:
                    if col in df.columns:
                        half_val = row[col]
                        full_val = row[col]
                        break
            else:
                for col in ['half ppr', 'half', '0.5 ppr', '0.5ppr', 'half-ppr']:
                    if col in df.columns:
                        half_val = row[col]
                        break
                
                for col in ['ppr', 'full ppr', '1 ppr', '1ppr', 'full', 'full-ppr']:
                    if col in df.columns:
                        full_val = row[col]
                        break
            
            def to_int(val):
                try:
                    if pd.isna(val):
                        return None
                    val_str = str(val).strip().replace(',', '')
                    if val_str == '' or val_str == '-':
                        return None
                    return int(float(val_str))
                except:
                    return None
            
            result.append({
                'PosRank': to_int(rank),
                'Name': str(name).strip(),
                'Position': position.upper(),
                'half_ppr': to_int(half_val),
                'full_ppr': to_int(full_val),
            })
        
        return pd.DataFrame(result)
        
    except Exception as e:
        print(f"[X] Error: {str(e)[:50]}")
        return pd.DataFrame()

# ---- Validation ----

def validate_against_previous_week(new_df: pd.DataFrame, week: int) -> None:
    """
    Compare new data against previous week's CSV to detect if values are suspiciously similar.
    Uses top 50 players per position and checks if >=95% have identical values.
    """
    prev_week = week - 1
    prev_path = os.path.join(DATA_DIR, f"boone_week{prev_week}.csv")
    
    if not os.path.exists(prev_path):
        return
    
    try:
        prev_df = pd.read_csv(prev_path)
    except Exception:
        return
    
    positions = ["QB", "RB", "WR", "TE"]
    total_compared = 0
    identical_count = 0
    
    for pos in positions:
        new_pos = new_df[new_df["Position"] == pos].head(50)
        prev_pos = prev_df[prev_df["Position"] == pos].head(50)
        
        prev_lookup = {}
        for _, row in prev_pos.iterrows():
            key = (str(row["Name"]).strip(), pos)
            prev_lookup[key] = (row.get("half_ppr"), row.get("full_ppr"))
        
        for _, new_row in new_pos.iterrows():
            name = str(new_row["Name"]).strip()
            key = (name, pos)
            
            if key in prev_lookup:
                total_compared += 1
                prev_half, prev_full = prev_lookup[key]
                new_half = new_row.get("half_ppr")
                new_full = new_row.get("full_ppr")
                
                half_same = (pd.isna(prev_half) and pd.isna(new_half)) or (prev_half == new_half)
                full_same = (pd.isna(prev_full) and pd.isna(new_full)) or (prev_full == new_full)
                
                if half_same and full_same:
                    identical_count += 1
    
    if total_compared == 0:
        return
    
    similarity_pct = (identical_count / total_compared) * 100
    
    if similarity_pct >= 95.0:
        print(f"[!] WARNING: {similarity_pct:.1f}% of values unchanged from Week {prev_week}")
        print(f"[!] Data may not have updated properly - please verify manually")
    else:
        print(f"[OK] Validation: {100 - similarity_pct:.1f}% of values changed from Week {prev_week}")

# ---- Main ----

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-week", type=int, default=None, help="Set new baseline week number (e.g., 2).")
    ap.add_argument("--baseline-tuesday", type=str, default=None, help="Set baseline Tuesday YYYY-MM-DD.")
    ap.add_argument("--headless", action="store_true", default=True, help="Run Chrome in headless mode (default: True).")
    ap.add_argument("--no-headless", action="store_false", dest="headless", help="Run Chrome with visible browser.")
    args = ap.parse_args()

    today = date.today()
    week, new_state = compute_week(today, args.reset_week, args.baseline_tuesday)
    save_state(new_state)

    print(f"[*] Scraping Boone Week {week} Trade Values\n")

    options = Options()
    if args.headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    service = Service(log_path=os.devnull)
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        urls = discover_trade_value_urls(week, driver)
        
        if not urls:
            print(f"\n[X] Could not auto-discover URLs for Week {week}")
            print("Please update the script with manual URLs or check if articles are published.")
            return
        
        print()
        all_dfs = []
        for pos in ["QB", "RB", "WR", "TE"]:
            if pos not in urls:
                print(f"[{pos}] [!] No URL found, skipping")
                continue
            
            df = scrape_position_table(urls[pos], pos, driver)
            if not df.empty:
                all_dfs.append(df)
        
        if not all_dfs:
            print("\n[X] No data scraped from any position")
            return
        
        total_players = sum(len(df) for df in all_dfs)
        print(f"\n[*] Total: {total_players} players scraped")
        
        out_df = pd.concat(all_dfs, ignore_index=True)
        
        pos_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
        out_df["__pos_order__"] = out_df["Position"].map(lambda x: pos_order.get(str(x).upper(), 9))
        out_df = out_df.sort_values(["__pos_order__", "PosRank", "Name"], kind="mergesort").drop(columns="__pos_order__")
        out_df = out_df.reset_index(drop=True)
        
        out_path = os.path.join(DATA_DIR, f"boone_week{week}.csv")
        out_df.to_csv(out_path, index=False)
        
        print()
        validate_against_previous_week(out_df, week)
        
        print(f"\n[OK] Saved to: {out_path}")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()