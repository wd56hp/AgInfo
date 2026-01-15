#!/bin/bash
# Run recalculate_facility_geom.py in a Python Docker container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read .env file values (handle BOM and comments)
if [ -f "$PROJECT_ROOT/.env" ]; then
    export POSTGRES_DB=$(grep -E "^POSTGRES_DB=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGRES_USER=$(grep -E "^POSTGRES_USER=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGRES_PASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
    export POSTGIS_HOST_PORT=$(grep -E "^POSTGIS_HOST_PORT=" "$PROJECT_ROOT/.env" | cut -d'=' -f2 | tr -d '\r' | xargs)
fi

# Database connection (from docker network perspective)
DB_HOST="${POSTGRES_HOST:-172.28.0.10}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

echo "AgInfo Facility Geometry Recalculation"
echo "======================================"
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo ""

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
        python3 recalculate_facility_geom.py ${PYTHON_ARGS}
    "

echo ""
echo "Geometry recalculation complete!"
