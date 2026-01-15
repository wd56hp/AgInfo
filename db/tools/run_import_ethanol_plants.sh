#!/bin/bash
# Run import_ethanol_plants.py in a Python Docker container
# This script runs the import script to add ethanol plants from CSV to the database

set -e

# Load environment variables from .env if it exists
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
DB_HOST="${POSTGRES_HOST:-172.28.0.10}"  # PostGIS container IP
DB_PORT="${POSTGRES_PORT:-5432}"  # Internal Docker port
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"

echo "AgInfo Ethanol Plant Import"
echo "==========================="
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo ""

# Default to db/temp/ethonal.csv if no file specified
if [ $# -eq 0 ]; then
    DEFAULT_CSV="${PROJECT_ROOT}/db/temp/ethonal.csv"
    if [ -f "$DEFAULT_CSV" ]; then
        echo "No file specified, using default: $DEFAULT_CSV"
        CSV_FILE="$DEFAULT_CSV"
        PYTHON_ARGS=""
    else
        echo "Usage: $0 [csv_file_path] [--apply]"
        echo ""
        echo "If no file is specified, will look for: ${DEFAULT_CSV}"
        echo ""
        echo "Example:"
        echo "  $0                                    # Uses ${DEFAULT_CSV}"
        echo "  $0 \"/path/to/ethonal.csv\"            # Dry run"
        echo "  $0 \"/path/to/ethonal.csv\" --apply   # Actually import"
        echo ""
        echo "Note: Use --apply to actually import data (default is dry run)"
        exit 1
    fi
else
    CSV_FILE="$1"
    shift
    PYTHON_ARGS="$@"
fi

# Check if CSV file exists (if it's a local path)
if [ ! -f "$CSV_FILE" ] && [[ ! "$CSV_FILE" =~ ^/mnt/ ]]; then
    echo "Warning: CSV file not found at: $CSV_FILE"
    echo "If this is a Windows path, you may need to copy it to the Linux filesystem first"
    echo "or mount it as a volume in Docker."
fi

# Run Python script in Docker container
docker run --rm \
    --network aginfo_aginfo-net \
    -v "${PROJECT_ROOT}:/project" \
    -v "${SCRIPT_DIR}:/app" \
    -v "$(dirname "$CSV_FILE"):/data" \
    -w /app \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    -e POSTGIS_HOST_PORT="${DB_PORT}" \
    -e PGHOST="${DB_HOST}" \
    python:3.11-slim \
    sh -c "
        pip install -q -r requirements.txt && \
        python import_ethanol_plants.py \"/data/$(basename "$CSV_FILE")\" $PYTHON_ARGS
    "
