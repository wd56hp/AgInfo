#!/bin/bash
# Run facility_geom_from_address.py in a Python Docker container
# This script runs the facility_geom_from_address.py script in a Python container

set -e

# Load environment variables from .env if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read .env file values (handle BOM and comments)
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Use grep to extract values, handling comments and empty lines
    export POSTGRES_DB=$(grep -E "^POSTGRES_DB=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGRES_USER=$(grep -E "^POSTGRES_USER=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGRES_PASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGIS_HOST_PORT=$(grep -E "^POSTGIS_HOST_PORT=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
fi

# Database connection (from docker network perspective)
DB_HOST="${POSTGRES_HOST:-172.28.0.10}"  # PostGIS container IP
DB_PORT="${POSTGRES_PORT:-5432}"  # Internal Docker port
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

echo "AgInfo Facility Geolocation Fix"
echo "================================"
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo ""

# Run Python script in Docker container
# Use the same network as the postgis container
# Mount the project root so .env file is accessible

# Run Python script in Docker container
# Use the same network as the postgis container
# Mount the project root so .env file is accessible

# Build the command with proper argument handling
if [ $# -eq 0 ]; then
    PYTHON_ARGS=""
else
    PYTHON_ARGS=$(printf '%q ' "$@")
    PYTHON_ARGS="${PYTHON_ARGS% }"  # Remove trailing space
fi

docker run --rm \
    --network aginfo_aginfo-net \
    -v "${PROJECT_ROOT}:/project" \
    -v "${SCRIPT_DIR}:/app" \
    -w /app \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    -e POSTGIS_HOST_PORT="${DB_PORT}" \
    -e PGHOST="${DB_HOST}" \
    python:3.11-slim \
    sh -c "
        pip install -q -r requirements.txt && \
        python3 facility_geom_from_address.py ${PYTHON_ARGS}
    "

echo ""
echo "Geolocation fix complete!"
