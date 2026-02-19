#!/bin/bash
#
# Real Estate Price Matching - Daily Pipeline (HARDENED)
# ========================================================
# 
# ALL-OR-NOTHING semantics:
# - Runs each step sequentially
# - Checks exit codes after EACH step
# - If market_scraper.py fails → abort, report failure
# - If export_deals.py fails → abort, report failure
# - Only git push if ALL steps succeeded
#
# Exit codes:
#   0 = success
#   1 = scraper failure
#   2 = export failure
#   3 = git failure
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date +'%H:%M:%S')] $1"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}" >&2
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓ $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠ $1${NC}"
}

# Change to project root
cd "$(dirname "$0")/.."

log "=========================================="
log "КЧСИ DAILY PIPELINE - HARDENED"
log "=========================================="
log "Started at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
log ""

# Step 1: Scrape auction data (bcpea_scraper.py)
log "Step 1/4: Scraping auction data (bcpea_scraper.py)..."
if python3 scrapers/bcpea_scraper.py --incremental; then
    success "Auction scraping complete"
else
    EXIT_CODE=$?
    error "Auction scraper failed with exit code $EXIT_CODE"
    exit 1
fi

# Step 2: Scrape market prices (market_scraper.py)
log ""
log "Step 2/4: Scraping market prices (market_scraper.py)..."
if python3 scrapers/market_scraper.py; then
    success "Market scraping complete"
else
    EXIT_CODE=$?
    error "Market scraper failed with exit code $EXIT_CODE"
    error "This means one or more sources did not return enough data"
    error "Check logs in data/logs/market_*.log for details"
    exit 1
fi

# Step 3: Export deals (join auction + market data)
log ""
log "Step 3/4: Exporting deals (export_deals.py)..."
if python3 export_deals.py; then
    success "Export complete"
else
    EXIT_CODE=$?
    error "Export failed with exit code $EXIT_CODE"
    exit 2
fi

# Step 4: Git push (only if everything succeeded)
log ""
log "Step 4/4: Pushing to GitHub..."
if ! git diff --quiet || ! git diff --cached --quiet; then
    DATE_STR=$(date -u +"%Y-%m-%d")
    git add -A
    git commit -m "data: Daily pipeline run $DATE_STR" --allow-empty || true
    
    if git push origin main; then
        success "Pushed to GitHub"
    else
        EXIT_CODE=$?
        warning "Git push failed with exit code $EXIT_CODE"
        warning "Data was scraped and exported successfully, but not pushed"
        exit 3
    fi
else
    log "No changes to commit"
fi

log ""
log "=========================================="
success "PIPELINE COMPLETE"
log "Finished at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
log "=========================================="

exit 0
