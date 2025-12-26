#!/bin/bash
# Script to update lookups.json with company names, facility type names, and website URLs from the database
# Run this whenever you add new companies or facility types to keep lookups.json in sync

# Auto-detect path: check if running on server or locally
if [ -d "/mnt/user/appdata/AgInfo" ]; then
    # Running on server
    BASE_DIR="/mnt/user/appdata/AgInfo"
    LOOKUPS_FILE="$BASE_DIR/web/data/lookups.json"
else
    # Running locally (assume script is in project root)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    BASE_DIR="$SCRIPT_DIR"
    LOOKUPS_FILE="$BASE_DIR/web/data/lookups.json"
fi

TEMP_FILE="/tmp/lookups_update.json"

# Create directory if it doesn't exist
mkdir -p "$(dirname "$LOOKUPS_FILE")"

# Create temporary JSON file with companies and facility types
echo '{' > "$TEMP_FILE"
echo '  "companies": {' >> "$TEMP_FILE"

# Get companies and format as JSON
docker exec aginfo-postgis psql -U agadmin -d aginfo -t -A -F'|' -c \
  "SELECT company_id, name FROM company ORDER BY company_id;" | \
while IFS='|' read -r company_id name; do
  if [ -n "$company_id" ] && [ -n "$name" ]; then
    # Escape quotes in company name
    name=$(echo "$name" | sed 's/"/\\"/g')
    echo "    \"$company_id\": \"$name\"," >> "$TEMP_FILE"
  fi
done

# Remove trailing comma from last company entry
sed -i '$ s/,$//' "$TEMP_FILE"
echo '  },' >> "$TEMP_FILE"

# Add facility types
echo '  "facilityTypes": {' >> "$TEMP_FILE"
docker exec aginfo-postgis psql -U agadmin -d aginfo -t -A -F'|' -c \
  "SELECT facility_type_id, name FROM facility_type ORDER BY facility_type_id;" | \
while IFS='|' read -r type_id name; do
  if [ -n "$type_id" ] && [ -n "$name" ]; then
    name=$(echo "$name" | sed 's/"/\\"/g')
    echo "    \"$type_id\": \"$name\"," >> "$TEMP_FILE"
  fi
done

# Remove trailing comma from last facility type entry
sed -i '$ s/,$//' "$TEMP_FILE"
echo '  },' >> "$TEMP_FILE"

# Add company websites
echo '  "companyWebsites": {' >> "$TEMP_FILE"
docker exec aginfo-postgis psql -U agadmin -d aginfo -t -A -F'|' -c \
  "SELECT company_id, COALESCE(website_url, '') FROM company ORDER BY company_id;" | \
while IFS='|' read -r company_id website_url; do
  if [ -n "$company_id" ]; then
    # Escape quotes in URL
    website_url=$(echo "$website_url" | sed 's/"/\\"/g')
    echo "    \"$company_id\": \"$website_url\"," >> "$TEMP_FILE"
  fi
done

# Remove trailing comma from last website entry
sed -i '$ s/,$//' "$TEMP_FILE"
echo '  }' >> "$TEMP_FILE"
echo '}' >> "$TEMP_FILE"

# Format JSON properly (if jq is available, use it; otherwise keep as is)
if command -v jq &> /dev/null; then
  jq . "$TEMP_FILE" > "$LOOKUPS_FILE"
else
  # Basic formatting - ensure proper indentation
  cp "$TEMP_FILE" "$LOOKUPS_FILE"
fi

# Clean up
rm -f "$TEMP_FILE"

echo "Updated $LOOKUPS_FILE with latest data from database"
COMPANY_COUNT=$(docker exec aginfo-postgis psql -U agadmin -d aginfo -t -c 'SELECT COUNT(*) FROM company;' | tr -d ' ')
WEBSITE_COUNT=$(docker exec aginfo-postgis psql -U agadmin -d aginfo -t -c "SELECT COUNT(*) FROM company WHERE website_url IS NOT NULL AND website_url != '';" | tr -d ' ')
TYPE_COUNT=$(docker exec aginfo-postgis psql -U agadmin -d aginfo -t -c 'SELECT COUNT(*) FROM facility_type;' | tr -d ' ')
echo "Companies: $COMPANY_COUNT"
echo "Companies with websites: $WEBSITE_COUNT"
echo "Facility Types: $TYPE_COUNT"


