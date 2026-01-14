#!/usr/bin/env bash
# Pull ignored/local-only files from Unraid server to local workstation
# Works from: WSL, Git Bash, cmd->wsl, PowerShell->wsl
# Avoids "hangs" by forcing non-interactive SSH (fails fast if auth isn't set up)

set +e

UNRAID_HOST="root@172.16.101.20"
UNRAID_PATH="/mnt/user/appdata/AgInfo"

# Detect whether we're running inside WSL
is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null
}

# Use WSL to run ssh/rsync when not already inside WSL (e.g., Git Bash on Windows)
if is_wsl; then
  RSYNC_CMD="${RSYNC_CMD:-rsync}"
  SSH_CMD="${SSH_CMD:-ssh}"
  echo "Detected environment: WSL"
else
  RSYNC_CMD="${RSYNC_CMD:-wsl rsync}"
  SSH_CMD="${SSH_CMD:-wsl ssh}"
  echo "Detected environment: Windows shell (using WSL for rsync/ssh)"
fi

# SSH options to prevent interactive prompts (password/hostkey) from hanging scripts
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o ServerAliveInterval=10 -o ServerAliveCountMax=2"

echo "=========================================="
echo "Pulling ignored files from Unraid server"
echo "=========================================="
echo "Host: $UNRAID_HOST"
echo "Path: $UNRAID_PATH"
echo "Using rsync: $RSYNC_CMD"
echo "Using ssh:   $SSH_CMD"
echo ""

echo "[1/3] Verifying rsync is available..."
$RSYNC_CMD --version >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "ERROR: rsync is not available via: $RSYNC_CMD"
  echo "If you're on Windows, ensure WSL is installed and rsync exists in your distro."
  exit 1
fi
echo "✓ rsync available"
echo ""

echo "[2/3] Testing SSH connection (non-interactive)..."
$SSH_CMD $SSH_OPTS "$UNRAID_HOST" "echo 'SSH OK'" >/dev/null 2>&1
SSH_TEST=$?
if [ $SSH_TEST -eq 0 ]; then
  echo "✓ SSH connection successful"
else
  echo "✗ SSH connection failed (code: $SSH_TEST)"
  echo "Most common causes:"
  echo "  - SSH key not set up for root@172.16.101.20"
  echo "  - Host unreachable / firewall"
  echo "Fix (inside WSL):"
  echo "  ssh-keygen -t ed25519"
  echo "  ssh-copy-id $UNRAID_HOST"
  echo ""
  echo "Aborting to avoid hanging on prompts."
  exit $SSH_TEST
fi
echo ""

echo "[3/3] Pulling .env file..."
$RSYNC_CMD -avz -e "ssh $SSH_OPTS" "${UNRAID_HOST}:${UNRAID_PATH}/.env" ./.env 2>&1
PULL_EXIT=$?
if [ $PULL_EXIT -eq 0 ]; then
  echo "✓ .env pulled successfully"
else
  echo "⚠ .env not found on server or pull failed (this is OK if file doesn't exist)"
fi

# Note: We don't pull db/data or geoserver/data_dir as they are large and gitignored for good reason
# If you need them locally, uncomment the following lines:
# echo "Pulling db/data directory (this may be large)..."
# mkdir -p ./db/data
# $RSYNC_CMD -avz -e "ssh $SSH_OPTS" "${UNRAID_HOST}:${UNRAID_PATH}/db/data/" ./db/data/ 2>&1 && echo "✓ db/data pulled" || echo "⚠ db/data not found on server"

# echo "Pulling geoserver/data_dir directory (this may be large)..."
# mkdir -p ./geoserver/data_dir
# $RSYNC_CMD -avz -e "ssh $SSH_OPTS" "${UNRAID_HOST}:${UNRAID_PATH}/geoserver/data_dir/" ./geoserver/data_dir/ 2>&1 && echo "✓ geoserver/data_dir pulled" || echo "⚠ geoserver/data_dir not found on server"

echo ""
echo "=========================================="
echo "✓ Pull complete!"
echo "=========================================="
echo ""
echo "Note: db/data and geoserver/data_dir are not pulled as they are large and gitignored."
echo "If you need them, uncomment the relevant lines in this script."
