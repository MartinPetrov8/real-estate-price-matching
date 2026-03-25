#!/usr/bin/env python3
"""
Real Estate Price Matching - Daily Pipeline Runner

Runs the full data pipeline:
1. Scrape imot.bg (requests)
2. Scrape OLX (Playwright)
3. Scrape alo.bg (requests)
4. Export deals with market comparison
5. Optionally push to GitHub
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
    result = subprocess.run(cmd.split() if isinstance(cmd, str) else cmd, cwd=cwd, capture_output=True, text=True, env=full_env)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        return False
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        for line in lines[-5:]:
            print(f"  {line}")
    return True

def check_deps():
    """Validate critical Python dependencies before pipeline starts."""
    missing = []
    dep_checks = [
        ("requests", "requests"),
        ("playwright", "playwright.sync_api"),
        ("bs4", "bs4"),
        ("sqlite3", "sqlite3"),
    ]
    for name, module in dep_checks:
        try:
            __import__(module)
        except ImportError:
            missing.append(name)
    if missing:
        log(f"❌ DEPENDENCY CHECK FAILED — missing: {', '.join(missing)}")
        log("   Run: /home/node/.openclaw/workspace/scripts/ensure-tools.sh")
        log("   Then re-run the pipeline.")
        sys.exit(2)
    log("✅ Dependency check passed (requests, playwright, bs4, sqlite3)")


def main():
    parser = argparse.ArgumentParser(description='Run the real estate data pipeline')
    parser.add_argument('--no-push', action='store_true', help='Skip git push')
    parser.add_argument('--market-only', action='store_true', help='Only run market scrapers')
    parser.add_argument('--export-only', action='store_true', help='Only run export')
    args = parser.parse_args()
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Pre-flight: verify all critical deps are present
    check_deps()
    
    log("=" * 60)
    log("REAL ESTATE PRICE MATCHING - DAILY PIPELINE")
    log("=" * 60)
    
    success = True
    pw_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    pw_env = {"PLAYWRIGHT_BROWSERS_PATH": pw_browsers_path} if pw_browsers_path else {}
    
    if not args.export_only:
        # Step 1: imot.bg scraper (requests)
        log("\n📊 Step 1/3: Scraping imot.bg...")
        if not run_cmd("python3 scrapers/market_scraper.py"):
            log("⚠️ imot.bg scraper had issues")
        else:
            log("✅ imot.bg complete")
        
        # Step 2: OLX scraper (Playwright)
        log("\n📊 Step 2/3: Scraping OLX (Playwright)...")
        if not run_cmd("python3 scrapers/olx_playwright.py", env=pw_env):
            log("⚠️ OLX scraper had issues")
        else:
            log("✅ OLX complete")
        
        # Step 3: alo.bg scraper (requests)
        log("\n📊 Step 3/3: Scraping alo.bg...")
        if not run_cmd("python3 scrapers/alo_scraper.py"):
            log("⚠️ alo.bg scraper had issues")
        else:
            log("✅ alo.bg complete")
    
    # Step 4: Export deals
    if not args.market_only:
        log("\n📤 Step 4: Exporting deals...")
        if not run_cmd("python3 export_deals.py"):
            log("❌ Export failed")
            success = False
        else:
            log("✅ Export complete")
    
    # Step 4b: Data coverage validation
    if not args.market_only and success:
        log("\n🔍 Step 4b: Validating data coverage...")
        try:
            import json
            with open('deals.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            deals = data.get('deals', [])
            total = len(deals)
            with_market = len([d for d in deals if d.get('market_avg')])
            coverage_pct = (with_market / total * 100) if total > 0 else 0
            log(f"  Total deals: {total}")
            log(f"  With market data: {with_market} ({coverage_pct:.1f}%)")
            if coverage_pct < 20:
                log(f"  ⚠️ COVERAGE ALERT: Only {coverage_pct:.1f}% of deals have market data (threshold: 20%)")
                log(f"  ⚠️ {total - with_market} deals will be hidden from users without market comparison")
            else:
                log(f"  ✅ Coverage OK ({coverage_pct:.1f}% ≥ 20%)")
        except Exception as e:
            log(f"  ⚠️ Coverage check failed: {e}")
    
    # Step 5: Git push
    if not args.no_push and not args.market_only and success:
        log("\n🚀 Step 5: Pushing to GitHub...")
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
