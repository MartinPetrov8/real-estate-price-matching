#!/bin/bash
#
# Real Estate Price Matching - Daily Pipeline (RESILIENT)
# ========================================================
# 
# ALL-OR-NOTHING with checkpoint/resume:
# - First attempt: fresh run
# - If market scraper interrupted (exit 2): auto-retry with --resume
# - Max 3 attempts before giving up
# - Only exports and pushes when ALL steps succeed
#
# Exit codes:
#   0 = success
#   1 = scraper failure (data issue, not resumable)
#   2 = export failure
#   3 = git failure
#   4 = max retries exhausted
#

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Python interpreter — system python3 has all deps (requests, bs4, lxml, certifi)
# The old competitor-tracker venv is gone; system python works fine.
PYTHON="python3"

log() { echo -e "[$(date +'%H:%M:%S')] $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}" >&2; }
success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓ $1${NC}"; }
warning() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠ $1${NC}"; }

cd "$(dirname "$0")/.."

MAX_RETRIES=3

log "=========================================="
log "КЧСИ DAILY PIPELINE - RESILIENT"
log "=========================================="
log "Started at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
log ""

# Step 1: Scrape auction data
log "Step 1/5: Scraping auction data (bcpea_scraper.py)..."
BCPEA_ATTEMPT=1
BCPEA_MAX_RETRIES=3
BCPEA_EXIT=1

while [ $BCPEA_ATTEMPT -le $BCPEA_MAX_RETRIES ]; do
    log "  Attempt $BCPEA_ATTEMPT/$BCPEA_MAX_RETRIES"
    
    if $PYTHON scrapers/bcpea_scraper.py --incremental; then
        BCPEA_EXIT=0
        success "Auction scraping complete"
        break
    else
        BCPEA_EXIT=$?
        warning "Auction scraper failed (attempt $BCPEA_ATTEMPT, exit $BCPEA_EXIT)"
        if [ $BCPEA_ATTEMPT -lt $BCPEA_MAX_RETRIES ]; then
            WAIT_SECS=$((30 * BCPEA_ATTEMPT))
            log "  Waiting ${WAIT_SECS}s before retry..."
            sleep $WAIT_SECS
        fi
        BCPEA_ATTEMPT=$((BCPEA_ATTEMPT + 1))
    fi
done

if [ $BCPEA_EXIT -ne 0 ]; then
    error "Auction scraper failed after $BCPEA_MAX_RETRIES attempts (last exit: $BCPEA_EXIT)"
    exit 1
fi

# Step 1.5: Geocode neighborhoods for new auctions (best-effort, non-blocking)
log ""
log "Step 1.5/5: Geocoding new auction neighborhoods..."
if $PYTHON scripts/geocode_neighborhoods.py 2>&1 | tail -10; then
    success "Geocoding complete"
else
    warning "Geocoding failed (non-critical, continuing)"
fi

# Step 2: Scrape market prices (with resume support)
log ""
log "Step 2/5: Scraping market prices (market_scraper.py)..."

ATTEMPT=1
RESUME_FLAG=""

while [ $ATTEMPT -le $MAX_RETRIES ]; do
    log "  Attempt $ATTEMPT/$MAX_RETRIES ${RESUME_FLAG:+(resuming)}"
    
    $PYTHON scrapers/market_scraper.py $RESUME_FLAG
    SCRAPER_EXIT=$?
    
    if [ $SCRAPER_EXIT -eq 0 ]; then
        success "Market scraping complete"
        break
    elif [ $SCRAPER_EXIT -eq 2 ]; then
        # Interrupted but checkpoint saved — retry with --resume
        warning "Market scraper interrupted (attempt $ATTEMPT), will resume..."
        RESUME_FLAG="--resume"
        ATTEMPT=$((ATTEMPT + 1))
        sleep 2
    else
        # Exit code 1 = hard failure (data issue)
        error "Market scraper failed with exit code $SCRAPER_EXIT"
        error "Check logs in data/logs/market_*.log"
        exit 1
    fi
done

if [ $SCRAPER_EXIT -ne 0 ]; then
    error "Market scraper failed after $MAX_RETRIES attempts"
    exit 4
fi

# Step 3: Export deals
log ""
log "Step 3/5: Exporting deals (export_deals.py)..."
if $PYTHON export_deals.py; then
    success "Export complete"
else
    EXIT_CODE=$?
    error "Export failed with exit code $EXIT_CODE"
    exit 2
fi

# Step 4: Git push
log ""
log "Step 4/5: Pushing to GitHub..."
if ! git diff --quiet || ! git diff --cached --quiet; then
    DATE_STR=$(date -u +"%Y-%m-%d")
    git add -A
    git commit -m "data: Daily pipeline run $DATE_STR" --allow-empty || true
    
    if git push origin main; then
        success "Pushed to GitHub"
    else
        EXIT_CODE=$?
        warning "Git push failed with exit code $EXIT_CODE"
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
