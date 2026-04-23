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
# - On any failure: sends Telegram alert to Martin
#
# Exit codes:
#   0 = success
#   1 = scraper failure (data issue, not resumable)
#   2 = export failure
#   3 = git failure
#   4 = max retries exhausted
#

set -uo pipefail

# ── Load GitHub credentials from git-credentials ──────────────────────────────
# In cron (isolated sessions), credential-cache is unavailable. credential-store
# reads from ~/.git-credentials which contains working classic PATs.
# Priority: GITHUB_TOKEN > GITHUB_BACKUP_TOKEN > first ghp_ PAT in store
export GITHUB_TOKEN="${GITHUB_TOKEN:-}"
export GITHUB_BACKUP_TOKEN="${GITHUB_BACKUP_TOKEN:-}"
if [ -z "$GITHUB_TOKEN" ] && [ -z "$GITHUB_BACKUP_TOKEN" ] && [ -f "$HOME/.git-credentials" ]; then
    # Extract first classic ghp_ PAT from git-credentials
    GHP_PAT=$(grep 'ghp_' "$HOME/.git-credentials" | head -1 | sed 's|.*://[^:]*:||' | sed 's|@github.com||')
    if [ -n "$GHP_PAT" ]; then
        export GITHUB_TOKEN="$GHP_PAT"
        log "Loaded GitHub credentials from git-credentials"
    fi
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Python interpreter with workspace-local packages (installed by ensure-tools.sh)
# ensure-tools.sh installs to /home/node/.openclaw/workspace/.local via pip --break-system-packages
# Set PYTHONPATH so python3 can find them regardless of pip install target
export PYTHONPATH="/home/node/.openclaw/workspace/.local/lib/python3.11/site-packages:${PYTHONPATH:-}"
PYTHON="python3"

log() { echo -e "[$(date +'%H:%M:%S')] $1"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}" >&2; }
success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓ $1${NC}"; }
warning() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠ $1${NC}"; }

cd "$(dirname "$0")/.."

# Ensure git works regardless of which user runs the cron
git config --global --add safe.directory "$(pwd)" 2>/dev/null || true

MAX_RETRIES=3          # Hard failures (data issues) — give up after 3
MAX_NET_WAIT=1800      # Network outage tolerance: wait up to 30min for connectivity

# ──────────────────────────────────────────────────────────
# ALERT: Send Telegram notification on pipeline failure
# ──────────────────────────────────────────────────────────
send_failure_alert() {
    local STEP="$1"
    local REASON="$2"
    local LOG_SNIPPET="$3"
    local TIMESTAMP
    TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")

    local MSG
    MSG="🚨 <b>КЧСИ pipeline FAILED</b>

Step: ${STEP}
Reason: ${REASON}
Time: ${TIMESTAMP}

Log:
${LOG_SNIPPET}

Last push: $(git log --oneline -1 2>/dev/null || echo 'unknown')
Fix: Check data/logs/market_$(date +%Y-%m-%d).log"

    # Send via Telegram Bot API (same pattern as docker-monitor.sh)
    local BOT_TOKEN
    BOT_TOKEN="$(jq -r '.channels.telegram.botToken' ~/.clawdbot/moltbot.json 2>/dev/null)"
    local CHAT_ID="6814975455"

    if [ -n "$BOT_TOKEN" ] && [ "$BOT_TOKEN" != "null" ]; then
        curl -s "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" \
            --data-urlencode "text=${MSG}" \
            -d "parse_mode=HTML" > /dev/null 2>&1 || true
        log "Alert sent to Telegram"
    else
        log "Warning: Could not load bot token for alert"
    fi
}

# ──────────────────────────────────────────────────────────
# NETWORK CHECK: Wait up to MAX_WAIT seconds for connectivity
# Default: 30 min (enough for a gateway restart + container up)
# ──────────────────────────────────────────────────────────
wait_for_network() {
    local MAX_WAIT="${1:-1800}"
    local ELAPSED=0
    local INTERVAL=15

    log "Checking network connectivity..."
    while ! curl -s --max-time 5 https://www.google.com >/dev/null 2>&1; do
        if [ $ELAPSED -ge $MAX_WAIT ]; then
            error "Network unavailable after ${MAX_WAIT}s — aborting"
            return 1
        fi
        warning "No network, waiting ${INTERVAL}s... (${ELAPSED}/${MAX_WAIT}s elapsed)"
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
    done
    success "Network OK"
    return 0
}

log "=========================================="
log "КЧСИ DAILY PIPELINE - RESILIENT"
log "=========================================="
log "Started at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
log ""

# Pre-flight: ensure network is up before doing anything
if ! wait_for_network; then
    send_failure_alert "Pre-flight network check" "DNS resolution failure — network unavailable at startup" "host www.olx.bg: NXDOMAIN / Name resolution failed"
    exit 1
fi

# Pre-flight: validate critical Python dependencies
log "Pre-flight: checking Python dependencies..."
DEP_CHECK_OUTPUT=$($PYTHON -c "
import sys
missing = []
for pkg, mod in [('requests','requests'), ('bs4','bs4'), ('sqlite3','sqlite3'), ('lxml','lxml')]:
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)
if missing:
    print('MISSING: ' + ', '.join(missing))
    sys.exit(2)
else:
    print('OK')
" 2>&1)
DEP_CHECK_EXIT=$?
if [ $DEP_CHECK_EXIT -ne 0 ]; then
    error "Dependency check FAILED: ${DEP_CHECK_OUTPUT}"
    log "Attempting to auto-restore deps via ensure-tools.sh..."
    if bash /Users/martin/.openclaw/workspace/scripts/ensure-tools.sh 2>&1 | tail -5; then
        log "ensure-tools.sh completed — retrying dep check..."
        if ! $PYTHON -c "import requests, bs4, lxml" 2>/dev/null; then
            send_failure_alert "Pre-flight dep check" "Missing: ${DEP_CHECK_OUTPUT}. ensure-tools.sh ran but deps still missing." "Run ensure-tools.sh manually"
            exit 1
        fi
        success "Deps restored OK"
    else
        send_failure_alert "Pre-flight dep check" "Missing: ${DEP_CHECK_OUTPUT}. ensure-tools.sh also failed." "Manual intervention needed"
        exit 1
    fi
else
    success "Dependency check passed (${DEP_CHECK_OUTPUT})"
fi

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
    LOG_SNIPPET=$(tail -20 data/logs/market_$(date +%Y-%m-%d).log 2>/dev/null || echo "No log available")
    send_failure_alert "Step 1 — bcpea_scraper.py" "Failed after ${BCPEA_MAX_RETRIES} attempts (exit ${BCPEA_EXIT})" "$LOG_SNIPPET"
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

# Step 2: Scrape market prices
# - Exit 0: success
# - Exit 2: interrupted (SIGTERM/network) — checkpoint saved, always resume after network back
#           Network interrupts do NOT count against MAX_RETRIES
# - Exit 1: hard data failure — counts against MAX_RETRIES, give up after 3
log ""
log "Step 2/5: Scraping market prices (market_scraper.py)..."

HARD_FAILURES=0
RESUME_FLAG=""

while true; do
    log "  Running market_scraper.py ${RESUME_FLAG:+(resuming from checkpoint)}"
    
    $PYTHON scrapers/market_scraper.py $RESUME_FLAG
    SCRAPER_EXIT=$?
    
    if [ $SCRAPER_EXIT -eq 0 ]; then
        success "Market scraping complete"
        break

    elif [ $SCRAPER_EXIT -eq 2 ]; then
        # Interrupted (SIGTERM, network drop) — checkpoint saved, just wait for network and resume
        warning "Market scraper interrupted — waiting for network to recover..."
        if wait_for_network "$MAX_NET_WAIT"; then
            RESUME_FLAG="--resume"
            log "  Network back — resuming in 10s..."
            sleep 10
            # Do NOT increment HARD_FAILURES — this was a transient interruption
        else
            LOG_SNIPPET=$(tail -20 data/logs/market_$(date +%Y-%m-%d).log 2>/dev/null || echo "No log available")
            send_failure_alert "Step 2 - market_scraper.py" "Network did not recover within ${MAX_NET_WAIT}s" "$LOG_SNIPPET"
            exit 1
        fi

    else
        # Exit 1: hard data failure — count against budget
        HARD_FAILURES=$((HARD_FAILURES + 1))
        error "Market scraper hard failure (exit $SCRAPER_EXIT, attempt $HARD_FAILURES/$MAX_RETRIES)"
        if [ $HARD_FAILURES -ge $MAX_RETRIES ]; then
            LOG_SNIPPET=$(tail -20 data/logs/market_$(date +%Y-%m-%d).log 2>/dev/null || echo "No log available")
            send_failure_alert "Step 2 - market_scraper.py" "Hard failure after ${MAX_RETRIES} attempts (exit ${SCRAPER_EXIT})" "$LOG_SNIPPET"
            exit 1
        fi
        log "  Retrying in 60s..."
        sleep 60
    fi
done

# Step 3: Export deals
log ""
log "Step 3/5: Exporting deals (export_deals.py)..."
if $PYTHON export_deals.py; then
    success "Export complete"
else
    EXIT_CODE=$?
    error "Export failed with exit code $EXIT_CODE"
    send_failure_alert "Step 3 — export_deals.py" "Export failed (exit ${EXIT_CODE})" "Check export_deals.py output"
    exit 2
fi

# Step 4: Git push
log ""
log "Step 4/5: Pushing to GitHub..."

# Verify git is functional first (catches safe.directory / ownership issues)
if ! git status >/dev/null 2>&1; then
    error "git status failed — likely ownership/safe.directory issue"
    send_failure_alert "Step 4 — git status" "git cannot operate on repo (ownership mismatch?)" "$(git status 2>&1 | head -5)"
    exit 3
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    DATE_STR=$(date -u +"%Y-%m-%d")
    git add -A
    git commit -m "data: Daily pipeline run $DATE_STR" --allow-empty || true
    
    # Prefer GITHUB_TOKEN (classic PAT from git-credentials), fallback to GITHUB_BACKUP_TOKEN (fine-grained PAT)
    PUSH_TOKEN="${GITHUB_TOKEN:-${GITHUB_BACKUP_TOKEN:-}}"
    # Also ensure credential helper can find ghp_ classic PAT from git-credentials
    git config --global credential.helper "store --file /home/node/.git-credentials"
    PUSH_URL="https://github.com/MartinPetrov8/real-estate-price-matching.git"
    if [ -n "$PUSH_TOKEN" ]; then
        PUSH_URL="https://${PUSH_TOKEN}@github.com/MartinPetrov8/real-estate-price-matching.git"
    else
        PUSH_URL="https://github.com/MartinPetrov8/real-estate-price-matching.git"
    fi
    if git push "$PUSH_URL" main; then
        success "Pushed to GitHub"
    else
        EXIT_CODE=$?
        warning "Git push failed with exit code $EXIT_CODE"
        send_failure_alert "Step 4 — git push" "Push to GitHub failed (exit ${EXIT_CODE})" "Check git credentials / network"
        exit 3
    fi
else
    log "No changes to commit"
fi

# Step 4.5: Verify the push actually landed
log ""
log "Step 4.5: Verifying git push landed..."
LAST_COMMIT_DATE=$(git log --format='%cd' --date=format:'%Y-%m-%d' -1 origin/main 2>/dev/null)
TODAY=$(date -u +"%Y-%m-%d")
if [ "$LAST_COMMIT_DATE" != "$TODAY" ]; then
    warning "Latest commit on origin/main is from $LAST_COMMIT_DATE, not today ($TODAY)"
    send_failure_alert "Step 4.5 — push verification" "Push may not have landed. Latest commit: $LAST_COMMIT_DATE" "Expected today: $TODAY"
    exit 3
fi
success "Push verified — latest commit is from today"

log ""
log "=========================================="
success "PIPELINE COMPLETE"
log "Finished at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
log "=========================================="

exit 0
