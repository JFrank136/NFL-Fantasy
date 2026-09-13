#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run all scrapers: Boone and DraftSharks
"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_scraper(script_name):
    """Run a scraper script and return success status."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    print(f"\n{'='*60}")
    print(f"Running {script_name}...")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run([sys.executable, script_path], 
                              cwd=SCRIPT_DIR,
                              check=True)
        print(f"\n✅ {script_name} completed successfully\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {script_name} failed with error code {e.returncode}\n")
        return False

def main():
    print("\n" + "="*60)
    print("RUNNING ALL SCRAPERS")
    print("="*60)
    
    # Run Boone
    boone_success = run_scraper("boone.py")
    
    # Run DraftSharks
    sharks_success = run_scraper("draftsharks.py")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Boone:        {'✅ Success' if boone_success else '❌ Failed'}")
    print(f"DraftSharks:  {'✅ Success' if sharks_success else '❌ Failed'}")
    print("="*60 + "\n")
    
    if not (boone_success and sharks_success):
        sys.exit(1)

if __name__ == "__main__":
    main()