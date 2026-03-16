#!/bin/bash
#
# КЧСИ Pipeline Watchdog
# ======================
# Runs every 30 minutes from 09:00–14:00 Sofia time.
# If the pipeline hasn't completed successfully today, re-fires it.
#
# Guards:
#   - Won't fire if pipeline is already running (PID lock)
#   - Won't fire after 14:00 Sofia time (give up for the day, alert instead)
#   - Won't fire if today's data already committed to git
#   - Max 3 recovery attempts per day
#

set -uo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/kchsi_pipeline.lock"
STATE_FILE="/tmp/kchsi_watchdog_$(date +%Y-%m-%d).state"
LOG_FILE="${PIPELINE_DIR}/data/logs/watchdog_$(date +%Y-%m-%d).log"

log() { echo "[$(date +'%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# ── Telegram alert ──────────────────────────────────────────
send_alert() {
    local MSG="$1"
    local BOT_TOKEN
    BOT_TOKEN="$(jq -r '.channels.telegram.botToken' ~/.clawdbot/moltbot.json 2>/dev/null)"
    local CHAT_ID="6814975455"
    if [ -n "$BOT_TOKEN" ] && [ "$BOT_TOKEN" != "null" ]; then
        curl -s "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" \
            --data-urlencode "text=${MSG}" \
            -d "parse_mode=HTML" > /dev/null 2>&1 || true
    fi
}

# ── Check if pipeline already succeeded today ───────────────
already_done() {
    cd "$PIPELINE_DIR" || return 1
    local TODAY
    TODAY=$(date -u +"%Y-%m-%d")
    # Check git log for today's commit
    git log --oneline --since="${TODAY} 00:00:00" --until="${TODAY} 23:59:59" 2>/dev/null \
        | grep -q "Daily pipeline run ${TODAY}"
}

# ── Check if pipeline is currently running ──────────────────
pipeline_running() {
    if [ -f "$LOCK_FILE" ]; then
        local PID
        PID=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            return 0  # running
        fi
        # Stale lock
        rm -f "$LOCK_FILE"
    fi
    return 1  # not running
}

# ── Read/write attempt counter ──────────────────────────────
get_attempts() {
    cat "$STATE_FILE" 2>/dev/null || echo "0"
}
inc_attempts() {
    local N
    N=$(get_attempts)
    echo $((N + 1)) > "$STATE_FILE"
}

# ── Main logic ───────────────────────────────────────────────
log "Watchdog triggered at $(date -u +'%Y-%m-%d %H:%M UTC')"

# 1. Already done today?
if already_done; then
    log "Pipeline already completed today — nothing to do"
    exit 0
fi

# 2. Already running?
if pipeline_running; then
    log "Pipeline already running (PID $(cat "$LOCK_FILE")) — skipping"
    exit 0
fi

# 3. Too many attempts today?
MAX_WATCHDOG_ATTEMPTS=3
ATTEMPTS=$(get_attempts)
if [ "$ATTEMPTS" -ge "$MAX_WATCHDOG_ATTEMPTS" ]; then
    log "Max watchdog attempts (${MAX_WATCHDOG_ATTEMPTS}) reached for today — giving up"
    send_alert "⚠️ <b>КЧСИ watchdog gave up</b>

Pipeline failed ${ATTEMPTS} auto-recovery attempts today.
Last git commit: $(cd "$PIPELINE_DIR" && git log --oneline -1 2>/dev/null || echo 'unknown')
Manual intervention needed."
    exit 1
fi

# 4. Past cutoff time (14:00 Sofia = 12:00 UTC)?
HOUR_UTC=$(date -u +"%H")
if [ "$HOUR_UTC" -ge 12 ]; then
    log "Past 14:00 Sofia time — not retrying, sending final alert"
    send_alert "⚠️ <b>КЧСИ pipeline still not done at 14:00</b>

${ATTEMPTS} auto-recovery attempt(s) made today.
Site data is stale. Manual action needed.
Last git push: $(cd "$PIPELINE_DIR" && git log --oneline -1 2>/dev/null || echo 'unknown')"
    exit 1
fi

# 5. Check if checkpoint exists (resume mode) or start fresh
RESUME_FLAG=""
TODAY=$(date -u +"%Y-%m-%d")
if [ -f "${PIPELINE_DIR}/data/checkpoint_${TODAY}.json" ]; then
    log "Checkpoint found for today — will resume"
    RESUME_FLAG="--resume"
fi

# 6. Fire the pipeline
inc_attempts
ATTEMPT_NUM=$(get_attempts)
log "Auto-recovery attempt ${ATTEMPT_NUM}/${MAX_WATCHDOG_ATTEMPTS} — firing pipeline (${RESUME_FLAG:-fresh start})"
send_alert "🔄 <b>КЧСИ watchdog auto-recovery</b>

Attempt ${ATTEMPT_NUM}/${MAX_WATCHDOG_ATTEMPTS}
Mode: ${RESUME_FLAG:-fresh start}
Time: $(date -u +'%Y-%m-%d %H:%M UTC')"

# Write PID lock
PIPELINE_LOG="${PIPELINE_DIR}/data/logs/pipeline_recovery_$(date +%Y%m%d_%H%M).log"
bash "${PIPELINE_DIR}/scripts/daily_pipeline.sh" \
    > "$PIPELINE_LOG" 2>&1 &
PIPELINE_PID=$!
echo "$PIPELINE_PID" > "$LOCK_FILE"

log "Pipeline started (PID ${PIPELINE_PID}), log: $PIPELINE_LOG"

# Wait for completion (watchdog stays alive to report result)
wait "$PIPELINE_PID"
PIPELINE_EXIT=$?
rm -f "$LOCK_FILE"

if [ "$PIPELINE_EXIT" -eq 0 ]; then
    log "Auto-recovery succeeded on attempt ${ATTEMPT_NUM}"
    send_alert "✅ <b>КЧСИ auto-recovery succeeded</b>

Attempt: ${ATTEMPT_NUM}/${MAX_WATCHDOG_ATTEMPTS}
Time: $(date -u +'%Y-%m-%d %H:%M UTC')
Data is now current."
    # Clear attempt counter on success
    rm -f "$STATE_FILE"
else
    log "Auto-recovery attempt ${ATTEMPT_NUM} failed (exit ${PIPELINE_EXIT})"
    # Alert already sent by daily_pipeline.sh on failure
fi

exit $PIPELINE_EXIT
