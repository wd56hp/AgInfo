#!/bin/bash
# Import SQL files from db/temp directory into PostgreSQL database via Docker
# Usage: ./import_via_docker.sh [pattern]
# Example: ./import_via_docker.sh "011*" to import files matching 011*

set -e

# Default values
CONTAINER_NAME="${POSTGIS_CONTAINER:-aginfo-postgis}"
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
TEMP_DIR="/tmp/aginfo-import"
PATTERN="${1:-*.sql}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}AgInfo Data Import Script (Docker)${NC}"
echo "=================================="
echo "Container: ${CONTAINER_NAME}"
echo "Database: ${DB_NAME}"
echo "User: ${DB_USER}"
echo "Pattern: ${PATTERN}"
echo "Temp directory (in container): ${TEMP_DIR}"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container '${CONTAINER_NAME}' is not running${NC}"
    exit 1
fi

# Find files matching the pattern inside the container, sorted by name
FILES=$(docker exec "$CONTAINER_NAME" sh -c "find ${TEMP_DIR} -maxdepth 1 -type f -name '${PATTERN}' | sort")

if [ -z "$FILES" ]; then
    echo -e "${YELLOW}Warning: No files found matching pattern: ${PATTERN}${NC}"
    echo "Make sure files are in ./db/temp/ directory on the host"
    exit 0
fi

# Count files
FILE_COUNT=$(echo "$FILES" | wc -l)
echo -e "${GREEN}Found ${FILE_COUNT} file(s) to import${NC}"
echo ""

# Import each file
SUCCESS_COUNT=0
FAIL_COUNT=0
FAILED_FILES=()

while IFS= read -r file; do
    if [ -n "$file" ]; then
        filename=$(basename "$file")
        echo -e "${YELLOW}Importing: ${filename}...${NC}"
        
        if docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -f "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}  ✓ Successfully imported: ${filename}${NC}"
            ((SUCCESS_COUNT++))
        else
            echo -e "${RED}  ✗ Failed to import: ${filename}${NC}"
            ((FAIL_COUNT++))
            FAILED_FILES+=("$filename")
        fi
    fi
done <<< "$FILES"

# Summary
echo ""
echo "=================================="
echo -e "${GREEN}Import Summary:${NC}"
echo "  Success: ${SUCCESS_COUNT}"
echo "  Failed:  ${FAIL_COUNT}"

if [ ${FAIL_COUNT} -gt 0 ]; then
    echo ""
    echo -e "${RED}Failed files:${NC}"
    for failed_file in "${FAILED_FILES[@]}"; do
        echo "  - ${failed_file}"
    done
    exit 1
fi

echo -e "${GREEN}All files imported successfully!${NC}"
exit 0

