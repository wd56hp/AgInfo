#!/bin/bash
# Script to help transfer ethonal.csv from Windows to db/temp directory
# This script can be run on the Unraid server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMP_DIR="${PROJECT_ROOT}/db/temp"

echo "Ethanol CSV Transfer Helper"
echo "==========================="
echo ""
echo "This script helps transfer ethonal.csv from Windows to:"
echo "  ${TEMP_DIR}"
echo ""

# Check if temp directory exists, create if not
if [ ! -d "$TEMP_DIR" ]; then
    echo "Creating temp directory: $TEMP_DIR"
    mkdir -p "$TEMP_DIR"
fi

# Method 1: Check if file is already in a mounted location
echo "Checking for file in common locations..."
POSSIBLE_LOCATIONS=(
    "/mnt/user/appdata/AgInfo/ethonal.csv"
    "/mnt/user/appdata/AgInfo/db/temp/ethonal.csv"
    "/mnt/disks/*/ethonal.csv"
    "/tmp/ethonal.csv"
)

FOUND=false
for loc in "${POSSIBLE_LOCATIONS[@]}"; do
    # Expand glob patterns
    for file in $loc; do
        if [ -f "$file" ]; then
            echo "✓ Found file at: $file"
            echo "  Copying to: ${TEMP_DIR}/ethonal.csv"
            cp "$file" "${TEMP_DIR}/ethonal.csv"
            FOUND=true
            break 2
        fi
    done
done

if [ "$FOUND" = true ]; then
    echo ""
    echo "✓ File successfully copied to: ${TEMP_DIR}/ethonal.csv"
    ls -lh "${TEMP_DIR}/ethonal.csv"
    exit 0
fi

echo ""
echo "File not found in common locations."
echo ""
echo "To transfer the file from Windows, you can use one of these methods:"
echo ""
echo "METHOD 1: SCP from Windows (if you have SSH access)"
echo "  From Windows PowerShell or Command Prompt:"
echo "    scp \"C:\\Users\\will.darrah\\OneDrive - Darrah Oil\\ethonal.csv\" user@DOC-UNRAID-SERV:/mnt/user/appdata/AgInfo/db/temp/"
echo ""
echo "METHOD 2: Copy via network share"
echo "  1. Map network drive to Unraid share"
echo "  2. Copy file to: \\\\DOC-UNRAID-SERV\\[share]\\appdata\\AgInfo\\db\\temp\\ethonal.csv"
echo ""
echo "METHOD 3: Use WinSCP or FileZilla"
echo "  Connect via SFTP and upload to: /mnt/user/appdata/AgInfo/db/temp/"
echo ""
echo "METHOD 4: Manual copy"
echo "  If you have the file accessible, you can copy it to:"
echo "    ${TEMP_DIR}/ethonal.csv"
echo ""
echo "After transferring, run the import script:"
echo "  ./db/tools/run_import_ethanol_plants.sh \"${TEMP_DIR}/ethonal.csv\""
echo ""

# If file path provided as argument, try to copy it
if [ $# -ge 1 ]; then
    SOURCE_FILE="$1"
    if [ -f "$SOURCE_FILE" ]; then
        echo "Copying file from: $SOURCE_FILE"
        cp "$SOURCE_FILE" "${TEMP_DIR}/ethonal.csv"
        echo "✓ File copied successfully!"
        ls -lh "${TEMP_DIR}/ethonal.csv"
    else
        echo "ERROR: Source file not found: $SOURCE_FILE"
        exit 1
    fi
fi
