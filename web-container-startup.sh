#!/bin/bash
# Script to run when aginfo-web container starts
# This updates lookups.json from the database

# Auto-detect path: check if running on server or locally
if [ -d "/mnt/user/appdata/AgInfo" ]; then
    # Running on server
    BASE_DIR="/mnt/user/appdata/AgInfo"
else
    # Running locally (assume script is in project root)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    BASE_DIR="$SCRIPT_DIR"
fi

UPDATE_SCRIPT="$BASE_DIR/update_lookups.sh"
INIT_SCRIPT="$BASE_DIR/init_lookups.sh"

# Wait for postgis container to be ready
echo "Waiting for database to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker exec aginfo-postgis pg_isready -U agadmin -d aginfo > /dev/null 2>&1; then
        echo "Database is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for database... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Database not ready after $MAX_RETRIES attempts. Continuing anyway..."
fi

# Initialize lookups.json if it doesn't exist, or update it if it does
if [ -f "$INIT_SCRIPT" ] && [ -x "$INIT_SCRIPT" ]; then
    "$INIT_SCRIPT"
elif [ -f "$UPDATE_SCRIPT" ] && [ -x "$UPDATE_SCRIPT" ]; then
    echo "Updating lookups.json from database..."
    "$UPDATE_SCRIPT"
else
    echo "Warning: Neither init_lookups.sh nor update_lookups.sh found or executable"
    echo "Lookups file may not be updated automatically."
fi

