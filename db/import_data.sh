#!/bin/bash
# Import SQL files from db/temp directory into PostgreSQL database
# Usage: ./import_data.sh [pattern]
# Example: ./import_data.sh "011*" to import files matching 011*

set -e

# Default values (can be overridden by environment variables)
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-15433}"
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
TEMP_DIR="${TEMP_DIR:-./db/temp}"

# Pattern to match files (default: all SQL files)
PATTERN="${1:-*.sql}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}AgInfo Data Import Script${NC}"
echo "=================================="
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo "User: ${DB_USER}"
echo "Pattern: ${PATTERN}"
echo "Temp directory: ${TEMP_DIR}"
echo ""

# Check if temp directory exists
if [ ! -d "$TEMP_DIR" ]; then
    echo -e "${RED}Error: Temp directory not found: ${TEMP_DIR}${NC}"
    exit 1
fi

# Find files matching the pattern, sorted by name
FILES=$(find "$TEMP_DIR" -maxdepth 1 -type f -name "$PATTERN" | sort)

if [ -z "$FILES" ]; then
    echo -e "${YELLOW}Warning: No files found matching pattern: ${PATTERN}${NC}"
    exit 0
fi

# Count files
FILE_COUNT=$(echo "$FILES" | wc -l)
echo -e "${GREEN}Found ${FILE_COUNT} file(s) to import${NC}"
echo ""

# Export password for psql (non-interactive)
export PGPASSWORD="$DB_PASSWORD"

# Import each file
SUCCESS_COUNT=0
FAIL_COUNT=0
FAILED_FILES=()

while IFS= read -r file; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        echo -e "${YELLOW}Importing: ${filename}...${NC}"
        
        if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$file" > /dev/null 2>&1; then
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

