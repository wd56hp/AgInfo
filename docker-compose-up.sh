#!/bin/bash
# Wrapper script for docker-compose up that runs web-container-startup.sh after web container starts

# Auto-detect path: check if running on server or locally
if [ -d "/mnt/user/appdata/AgInfo" ]; then
    # Running on server
    BASE_DIR="/mnt/user/appdata/AgInfo"
else
    # Running locally (assume script is in project root)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    BASE_DIR="$SCRIPT_DIR"
fi

cd "$BASE_DIR" || exit 1

STARTUP_SCRIPT="$BASE_DIR/web-container-startup.sh"

# Start containers in detached mode
echo "Starting AgInfo containers..."
docker-compose up -d

# Wait for web container to be running
echo "Waiting for web container to start..."
MAX_WAIT=30
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if docker ps --format '{{.Names}}' | grep -q "^aginfo-web$"; then
        if [ "$(docker inspect -f '{{.State.Running}}' aginfo-web)" = "true" ]; then
            echo "Web container is running!"
            break
        fi
    fi
    WAIT_COUNT=$((WAIT_COUNT + 1))
    sleep 1
done

# Run startup script to update lookups.json
if [ -f "$STARTUP_SCRIPT" ] && [ -x "$STARTUP_SCRIPT" ]; then
    echo "Running web container startup script..."
    "$STARTUP_SCRIPT"
else
    echo "Warning: web-container-startup.sh not found or not executable at $STARTUP_SCRIPT"
fi

echo "AgInfo stack is up and running!"
echo "Web: http://localhost:${WEB_HOST_PORT:-8091}"
echo "GeoServer: http://localhost:${GEOSERVER_HOST_PORT:-8090}"

