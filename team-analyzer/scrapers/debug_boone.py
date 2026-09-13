#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug script to inspect Justin Boone's author page and see what articles are available.
This will help us fix the auto-discovery mechanism.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os

AUTHOR_PAGE = "https://sports.yahoo.com/author/justin-boone/"

def main():
    print("🔍 DEBUG: Inspecting Justin Boone's author page...\n")
    
    options = Options()
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
        driver.set_page_load_timeout(30)
        print(f"📍 Navigating to: {AUTHOR_PAGE}")
        driver.get(AUTHOR_PAGE)
        time.sleep(5)
        
        current_url = driver.current_url
        print(f"📍 Current URL: {current_url}")
        
        page_title = driver.title
        print(f"📄 Page Title: {page_title}\n")
        
        # Click Articles tab
        print("📑 Attempting to click Articles tab...")
        try:
            label = driver.find_element(By.XPATH, "//label[contains(text(), 'Articles')]")
            label.click()
            time.sleep(3)
            print("✅ Articles tab clicked\n")
        except Exception as e:
            print(f"⚠️  Could not click Articles tab: {e}\n")
        
        print("✅ Skipping scroll (avoiding timeout)\n")
        
        # Wait a bit more for dynamic content to load
        print("⏳ Waiting for articles to load...")
        time.sleep(5)
        
        # Try to find article containers/cards instead of just links
        print("🔎 Trying different selectors...\n")
        
        # Method 1: Look for h3/h4/h2 elements (common for article titles)
        title_elements = driver.find_elements(By.XPATH, "//h2 | //h3 | //h4")
        print(f"📰 Found {len(title_elements)} heading elements")
        
        # Method 2: Look for specific article/fantasy URLs in href
        article_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/fantasy/article/')]")
        print(f"🏈 Found {len(article_links)} /fantasy/article/ links")
        
        # Method 3: Any link with Justin Boone or Week in visible text
        all_links = driver.find_elements(By.TAG_NAME, "a")
        print(f"🔗 Found {len(all_links)} total links\n")
        
        print("=" * 80)
        print("CHECKING ARTICLE LINKS WITH /fantasy/article/ IN URL:")
        print("=" * 80)
        
        # Output fantasy article links
        count = 0
        for i, link in enumerate(article_links, 1):
            try:
                # Try multiple ways to get text
                text_direct = link.text.strip() if link.text else ""
                
                # Try to get text from parent or nearby elements if link text is empty
                text_parent = ""
                if not text_direct:
                    try:
                        parent = link.find_element(By.XPATH, "..")
                        text_parent = parent.text.strip() if parent.text else ""
                    except:
                        pass
                
                href = link.get_attribute('href')
                
                print(f"\n[Fantasy Article #{i}]")
                print(f"Direct Text: '{text_direct}' (length: {len(text_direct)})")
                if text_parent:
                    print(f"Parent Text: '{text_parent[:100]}...' (length: {len(text_parent)})")
                print(f"URL: {href if href else 'NO URL'}")
                
                # Use whichever text source has content
                text = text_parent if not text_direct and text_parent else text_direct
                
                if not text:
                    print("No text found in direct or parent")
                    print("-" * 80)
                    continue
                
                count += 1
                
                # Check for various keywords
                text_lower = text.lower()
                keywords_found = []
                
                if "trade value" in text_lower:
                    keywords_found.append("trade value")
                if "rest of season" in text_lower:
                    keywords_found.append("rest of season")
                if "ranking" in text_lower:
                    keywords_found.append("ranking")
                if "for week" in text_lower:
                    keywords_found.append("for week")
                if "prior to week" in text_lower:
                    keywords_found.append("prior to week")
                if "week 13" in text_lower:
                    keywords_found.append("week 13")
                if "quarterback" in text_lower or "qb" in text_lower:
                    keywords_found.append("QB")
                if "running back" in text_lower or "running-back" in text_lower:
                    keywords_found.append("RB")
                if "wide receiver" in text_lower or "wide-receiver" in text_lower:
                    keywords_found.append("WR")
                if "tight end" in text_lower or "tight-end" in text_lower:
                    keywords_found.append("TE")
                
                if keywords_found:
                    print(f"[OK] Keywords: {', '.join(keywords_found)}")
                else:
                    print("No relevant keywords found")
                
                print("-" * 80)
                
                if count >= 20:
                    break
                
            except Exception as e:
                print(f"\n[Article #{i}] - Error: {e}")
                print("-" * 80)
        
        print("\n" + "=" * 80)
        print("🎯 DEBUG COMPLETE")
        print("\nPlease copy ALL the output above and send it back.")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()