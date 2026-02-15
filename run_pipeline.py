#!/usr/bin/env python3
"""
Real Estate Price Matching - Daily Pipeline Runner

Runs the full data pipeline:
1. Scrape market data (imot.bg, olx.bg)
2. Export deals with market comparison
3. Optionally push to GitHub

Usage:
    python run_pipeline.py              # Full pipeline
    python run_pipeline.py --no-push    # Without git push
    python run_pipeline.py --market-only # Only market scrape
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime

def log(msg):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_cmd(cmd, cwd=None):
    """Run command and return success status."""
    log(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        return False
    if result.stdout:
        # Print last few lines
        lines = result.stdout.strip().split('\n')
        for line in lines[-5:]:
            print(f"  {line}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Run the real estate data pipeline')
    parser.add_argument('--no-push', action='store_true', help='Skip git push')
    parser.add_argument('--market-only', action='store_true', help='Only run market scraper')
    parser.add_argument('--export-only', action='store_true', help='Only run export')
    args = parser.parse_args()
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    log("=" * 60)
    log("REAL ESTATE PRICE MATCHING - DAILY PIPELINE")
    log("=" * 60)
    
    success = True
    
    # Step 1: Market scraper
    if not args.export_only:
        log("\n📊 Step 1: Scraping market data...")
        if not run_cmd("python3 scrapers/market_scraper.py"):
            log("❌ Market scraper failed")
            success = False
        else:
            log("✅ Market scraper complete")
    
    # Step 2: Export deals
    if not args.market_only:
        log("\n📤 Step 2: Exporting deals...")
        if not run_cmd("python3 export_deals.py"):
            log("❌ Export failed")
            success = False
        else:
            # Copy to root for GitHub Pages
            run_cmd("cp frontend/deals.json deals.json")
            log("✅ Export complete")
    
    # Step 3: Git push
    if not args.no_push and not args.market_only and success:
        log("\n🚀 Step 3: Pushing to GitHub...")
        date_str = datetime.now().strftime('%Y-%m-%d')
        run_cmd("git add -A")
        run_cmd(f'git commit -m "data: Daily pipeline run {date_str}" --allow-empty')
        if not run_cmd("git push origin main"):
            log("⚠️ Git push failed (may need auth)")
        else:
            log("✅ Pushed to GitHub")
    
    log("\n" + "=" * 60)
    if success:
        log("✅ PIPELINE COMPLETE")
    else:
        log("⚠️ PIPELINE COMPLETED WITH ERRORS")
    log("=" * 60)
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
