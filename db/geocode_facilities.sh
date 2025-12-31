#!/bin/bash
# Geocode facilities using a Python Docker container
# This script runs the geocode_facilities.py script in a Python container

set -e

# Load environment variables from .env if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables from .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Database connection (from docker network perspective)
DB_HOST="${POSTGRES_HOST:-172.28.0.10}"  # PostGIS container IP
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "AgInfo Facility Geocoding"
echo "=========================="
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo ""

# Run Python script in Docker container
# Use the same network as the postgis container
docker run --rm \
    --network aginfo_aginfo-net \
    -v "${SCRIPT_DIR}:/app" \
    -w /app \
    -e POSTGRES_HOST="${DB_HOST}" \
    -e POSTGRES_PORT="${DB_PORT}" \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    python:3.11-slim \
    sh -c "
        pip install -q psycopg2-binary requests && \
        python3 geocode_facilities.py
    "

echo ""
echo "Geocoding complete!"
