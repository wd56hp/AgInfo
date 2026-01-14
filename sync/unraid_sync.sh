#!/usr/bin/env bash
# Sync local code to Unraid server for testing without committing
# Works from: WSL, Git Bash, cmd->wsl, PowerShell->wsl
# Avoids "hangs" by forcing non-interactive SSH (fails fast if auth isn't set up)

set +e

UNRAID_HOST="root@172.16.101.20"
UNRAID_PATH="/mnt/user/appdata/AgInfo"

# Get script directory and ensure logs directory exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

START_TIME=$(date +%s)
LOG_FILE="$LOG_DIR/sync_$(date +%Y%m%d_%H%M%S).log"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Detect whether we're running inside WSL
is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null
}

# Use WSL to run ssh/rsync when not already inside WSL (e.g., Git Bash on Windows)
if is_wsl; then
  RSYNC_CMD="${RSYNC_CMD:-rsync}"
  SSH_CMD="${SSH_CMD:-ssh}"
  log "Detected environment: WSL"
else
  RSYNC_CMD="${RSYNC_CMD:-wsl rsync}"
  SSH_CMD="${SSH_CMD:-wsl ssh}"
  log "Detected environment: Windows shell (using WSL for rsync/ssh)"
fi

# SSH options to prevent interactive prompts (password/hostkey) from hanging scripts
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o ServerAliveInterval=10 -o ServerAliveCountMax=2"

log "=========================================="
log "Starting sync script"
log "Log file: $LOG_FILE"
log "Host: $UNRAID_HOST"
log "Path: $UNRAID_PATH"
log "Using rsync: $RSYNC_CMD"
log "Using ssh:   $SSH_CMD"
log "=========================================="
log ""

log "[1/4] Verifying rsync is available..."
# Verify rsync exists (works for both "rsync" and "wsl rsync")
$RSYNC_CMD --version >/dev/null 2>&1
if [ $? -ne 0 ]; then
  log "ERROR: rsync is not available via: $RSYNC_CMD"
  log "If you're on Windows, ensure WSL is installed and rsync exists in your distro."
  exit 1
fi
log "✓ rsync available"
log ""

log "[2/4] Testing SSH connection (non-interactive)..."
$SSH_CMD $SSH_OPTS "$UNRAID_HOST" "echo 'SSH OK'" >/dev/null 2>&1
SSH_TEST=$?
if [ $SSH_TEST -eq 0 ]; then
  log "✓ SSH connection successful"
else
  log "✗ SSH connection failed (code: $SSH_TEST)"
  log "Most common causes:"
  log "  - SSH key not set up for root@172.16.101.20"
  log "  - Host unreachable / firewall"
  log "Fix (inside WSL):"
  log "  ssh-keygen -t ed25519"
  log "  ssh-copy-id $UNRAID_HOST"
  log ""
  log "Aborting to avoid rsync hanging on prompts."
  exit $SSH_TEST
fi
log ""

log "[3/4] Dry-run to estimate changes..."
log "Excluding: .git, db/data, geoserver/data_dir, Temp/temp, build artifacts, venvs, caches, node_modules, backups"
log ""

# NOTE: Use a single tee (no tail) to avoid hiding prompts/errors and to prevent buffering confusion.
$RSYNC_CMD -avz --delete --dry-run --stats \
  -e "ssh $SSH_OPTS" \
  --exclude ".git" \
  --exclude "db/data" \
  --exclude "geoserver/data_dir" \
  --exclude "Temp" \
  --exclude "temp" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "*.pyo" \
  --exclude "*.pyd" \
  --exclude ".DS_Store" \
  --exclude "Thumbs.db" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude "env" \
  --exclude "ENV" \
  --exclude "node_modules" \
  --exclude ".pytest_cache" \
  --exclude ".mypy_cache" \
  --exclude ".ruff_cache" \
  --exclude "*.egg-info" \
  --exclude "dist" \
  --exclude "build" \
  --exclude "*.tmp" \
  --exclude "*.temp" \
  --exclude "backups" \
  --exclude "*.backup" \
  --exclude "*.dump" \
  --exclude "*.sql.gz" \
  --exclude "*.tar.gz" \
  ./ "${UNRAID_HOST}:${UNRAID_PATH}/" 2>&1 | tee -a "$LOG_FILE"

DRYRUN_EXIT=$?
if [ $DRYRUN_EXIT -ne 0 ]; then
  log ""
  log "✗ Dry-run failed (exit code: $DRYRUN_EXIT). Aborting."
  exit $DRYRUN_EXIT
fi

log ""
log "Starting actual sync..."
log ""

log "[4/4] Executing rsync transfer..."
$RSYNC_CMD -avz --delete --progress --stats \
  -e "ssh $SSH_OPTS" \
  --exclude ".git" \
  --exclude "db/data" \
  --exclude "geoserver/data_dir" \
  --exclude "Temp" \
  --exclude "temp" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "*.pyo" \
  --exclude "*.pyd" \
  --exclude ".DS_Store" \
  --exclude "Thumbs.db" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude "env" \
  --exclude "ENV" \
  --exclude "node_modules" \
  --exclude ".pytest_cache" \
  --exclude ".mypy_cache" \
  --exclude ".ruff_cache" \
  --exclude "*.egg-info" \
  --exclude "dist" \
  --exclude "build" \
  --exclude "*.tmp" \
  --exclude "*.temp" \
  --exclude "backups" \
  --exclude "*.backup" \
  --exclude "*.dump" \
  --exclude "*.sql.gz" \
  --exclude "*.tar.gz" \
  ./ "${UNRAID_HOST}:${UNRAID_PATH}/" 2>&1 | tee -a "$LOG_FILE"

SYNC_EXIT_CODE=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

log ""
log "=========================================="
log "Sync process completed"
log "Duration: ${MINUTES}m ${SECONDS}s"
log "Log file saved to: $LOG_FILE"
log "=========================================="

if [ $SYNC_EXIT_CODE -eq 0 ]; then
  log "✓ Sync complete! Code is now on Unraid server."
  log "To restart services (example):"
  log "  $SSH_CMD $SSH_OPTS $UNRAID_HOST 'cd $UNRAID_PATH && docker-compose down && docker-compose up -d'"
  exit 0
else
  log "✗ Sync failed with exit code: $SYNC_EXIT_CODE"
  exit $SYNC_EXIT_CODE
fi
