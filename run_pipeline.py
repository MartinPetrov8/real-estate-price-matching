#!/usr/bin/env python3
"""
Real Estate Price Matching - Daily Pipeline Runner

Runs the full data pipeline:
1. Scrape market data (imot.bg via requests)
2. Scrape OLX data (Playwright - bypasses CAPTCHA)
3. Export deals with market comparison
4. Optionally push to GitHub

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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_cmd(cmd, cwd=None, env=None):
    log(f"Running: {cmd}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, env=full_env)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        return False
    if result.stdout:
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
    
    # Playwright browsers path
    pw_env = {"PLAYWRIGHT_BROWSERS_PATH": "/host-workspace/.playwright-browsers"}
    
    # Step 1: imot.bg scraper (requests-based)
    if not args.export_only:
        log("\n📊 Step 1: Scraping imot.bg...")
        if not run_cmd("python3 scrapers/market_scraper.py"):
            log("⚠️ imot.bg scraper had issues")
        else:
            log("✅ imot.bg complete")
    
    # Step 2: OLX scraper (Playwright)
    if not args.export_only:
        log("\n📊 Step 2: Scraping OLX (Playwright)...")
        if not run_cmd("python3 scrapers/olx_playwright.py", env=pw_env):
            log("⚠️ OLX scraper had issues")
        else:
            log("✅ OLX complete")
    
    # Step 3: Export deals
    if not args.market_only:
        log("\n📤 Step 3: Exporting deals...")
        if not run_cmd("python3 export_deals.py"):
            log("❌ Export failed")
            success = False
        else:
            log("✅ Export complete")
    
    # Step 4: Git push
    if not args.no_push and not args.market_only and success:
        log("\n🚀 Step 4: Pushing to GitHub...")
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
