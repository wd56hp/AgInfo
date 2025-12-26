#!/bin/bash
# Script to initialize lookups.json if it doesn't exist
# This is useful for new installations

# Auto-detect path: check if running on server or locally
if [ -d "/mnt/user/appdata/AgInfo" ]; then
    # Running on server
    BASE_DIR="/mnt/user/appdata/AgInfo"
    LOOKUPS_FILE="$BASE_DIR/web/data/lookups.json"
    UPDATE_SCRIPT="$BASE_DIR/update_lookups.sh"
else
    # Running locally (assume script is in project root)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    BASE_DIR="$SCRIPT_DIR"
    LOOKUPS_FILE="$BASE_DIR/web/data/lookups.json"
    UPDATE_SCRIPT="$BASE_DIR/update_lookups.sh"
fi

# Create directory if it doesn't exist
mkdir -p "$(dirname "$LOOKUPS_FILE")"

# Check if lookups.json exists
if [ ! -f "$LOOKUPS_FILE" ]; then
    echo "lookups.json not found. Creating it from database..."
    
    # Check if update_lookups.sh exists and is executable
    if [ -f "$UPDATE_SCRIPT" ] && [ -x "$UPDATE_SCRIPT" ]; then
        "$UPDATE_SCRIPT"
    else
        echo "Error: update_lookups.sh not found or not executable at $UPDATE_SCRIPT"
        echo "Creating empty lookups.json structure..."
        
        # Create minimal structure
        cat > "$LOOKUPS_FILE" << 'EOF'
{
  "companies": {},
  "facilityTypes": {},
  "companyWebsites": {}
}
EOF
        echo "Created empty lookups.json at $LOOKUPS_FILE"
        echo "Run update_lookups.sh to populate it from the database."
        exit 1
    fi
else
    echo "lookups.json already exists at $LOOKUPS_FILE"
fi

