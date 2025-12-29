#!/bin/bash
# AgInfo Backup Script (Bash)
# Creates a complete backup of database and application data

set -e

# Load .env file if it exists
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Default values (use environment variable if set, otherwise default)
BACKUP_DIR="${BACKUP_DIR:-backups}"
COMPRESS=false
SKIP_GEOSERVER=false
SKIP_WEB=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --compress)
            COMPRESS=true
            shift
            ;;
        --skip-geoserver)
            SKIP_GEOSERVER=true
            shift
            ;;
        --skip-web)
            SKIP_WEB=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--backup-dir DIR] [--compress] [--skip-geoserver] [--skip-web]"
            exit 1
            ;;
    esac
done

# Get timestamp for backup directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="$BACKUP_DIR/aginfo_backup_$TIMESTAMP"

echo "========================================"
echo "AgInfo Backup Script"
echo "========================================"
echo "Backup Directory: $BACKUP_PATH"
echo ""

# Create backup directory structure
mkdir -p "$BACKUP_PATH"/{database,geoserver,web,django,config}

# Check if Docker containers are running
echo "Checking Docker containers..."
POSTGIS_RUNNING=$(docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | grep -q "aginfo-postgis" && echo "yes" || echo "no")
GEOSERVER_RUNNING=$(docker ps --filter "name=aginfo-geoserver" --format "{{.Names}}" | grep -q "aginfo-geoserver" && echo "yes" || echo "no")

if [ "$POSTGIS_RUNNING" != "yes" ]; then
    echo "WARNING: PostGIS container is not running. Database backup may fail."
fi

# Backup Database
echo ""
echo "Backing up PostgreSQL database..."
# Get database credentials from environment or use defaults
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
DB_HOST="${POSTGIS_HOST_PORT:-localhost:15433}"

DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.dump"

echo "  Exporting database to: $DUMP_FILE"
if docker exec aginfo-postgis pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f /tmp/aginfo_backup.dump 2>/dev/null; then
    docker cp aginfo-postgis:/tmp/aginfo_backup.dump "$DUMP_FILE"
    docker exec aginfo-postgis rm /tmp/aginfo_backup.dump
    
    DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    echo "  ✓ Database backup complete ($DUMP_SIZE)"
else
    echo "  ✗ Database backup failed"
    echo "  Continuing with other backups..."
fi

# Backup GeoServer data
if [ "$SKIP_GEOSERVER" != "true" ]; then
    echo ""
    echo "Backing up GeoServer data..."
    if [ -d "geoserver/data_dir" ]; then
        echo "  Copying GeoServer data directory..."
        cp -r geoserver/data_dir "$BACKUP_PATH/geoserver/"
        
        GEOSERVER_SIZE=$(du -sh "$BACKUP_PATH/geoserver/data_dir" | cut -f1)
        echo "  ✓ GeoServer backup complete ($GEOSERVER_SIZE)"
    else
        echo "  ⚠ GeoServer data directory not found, skipping..."
    fi
else
    echo ""
    echo "Skipping GeoServer backup (--skip-geoserver flag)"
fi

# Backup Web files
if [ "$SKIP_WEB" != "true" ]; then
    echo ""
    echo "Backing up web files..."
    if [ -d "web" ]; then
        echo "  Copying web directory..."
        cp -r web "$BACKUP_PATH/"
        
        WEB_SIZE=$(du -sh "$BACKUP_PATH/web" | cut -f1)
        echo "  ✓ Web files backup complete ($WEB_SIZE)"
    else
        echo "  ⚠ Web directory not found, skipping..."
    fi
else
    echo ""
    echo "Skipping web files backup (--skip-web flag)"
fi

# Backup Django static and media files
echo ""
echo "Backing up Django files..."
if [ -d "aginfo_django/staticfiles" ]; then
    echo "  Copying Django static files..."
    cp -r aginfo_django/staticfiles "$BACKUP_PATH/django/"
fi

if [ -d "aginfo_django/media" ]; then
    echo "  Copying Django media files..."
    cp -r aginfo_django/media "$BACKUP_PATH/django/"
fi

if [ -d "aginfo_django/staticfiles" ] || [ -d "aginfo_django/media" ]; then
    echo "  ✓ Django files backup complete"
else
    echo "  ⚠ Django static/media directories not found, skipping..."
fi

# Backup configuration files
echo ""
echo "Backing up configuration files..."
CONFIG_DEST="$BACKUP_PATH/config"

# Backup .env files (if they exist)
if [ -f ".env" ]; then
    cp .env "$CONFIG_DEST/.env"
    echo "  ✓ .env file backed up"
fi

# Backup docker-compose.yml
if [ -f "docker-compose.yml" ]; then
    cp docker-compose.yml "$CONFIG_DEST/docker-compose.yml"
fi

# Backup Django settings (for reference)
if [ -f "aginfo_django/settings.py" ]; then
    cp aginfo_django/settings.py "$CONFIG_DEST/settings.py"
fi

echo "  ✓ Configuration files backed up"

# Create backup manifest
echo ""
echo "Creating backup manifest..."
cat > "$BACKUP_PATH/manifest.json" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "date": "$(date +"%Y-%m-%d %H:%M:%S")",
  "backup_path": "$BACKUP_PATH",
  "database": {
    "name": "$DB_NAME",
    "user": "$DB_USER",
    "host": "$DB_HOST",
    "backup_file": "database/aginfo_backup.dump"
  },
  "components": {
    "database": true,
    "geoserver": $([ "$SKIP_GEOSERVER" != "true" ] && echo "true" || echo "false"),
    "web": $([ "$SKIP_WEB" != "true" ] && echo "true" || echo "false"),
    "django": true,
    "config": true
  }
}
EOF
echo "  ✓ Manifest created"

# Compress backup if requested
if [ "$COMPRESS" = "true" ]; then
    echo ""
    echo "Compressing backup..."
    ZIP_FILE="$BACKUP_PATH.tar.gz"
    tar -czf "$ZIP_FILE" -C "$BACKUP_DIR" "aginfo_backup_$TIMESTAMP"
    
    ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
    echo "  ✓ Backup compressed ($ZIP_SIZE)"
    
    # Optionally remove uncompressed backup
    echo "  Removing uncompressed backup..."
    rm -rf "$BACKUP_PATH"
    echo "  ✓ Compression complete"
fi

# Summary
echo ""
echo "========================================"
echo "Backup Complete!"
echo "========================================"
echo "Backup location: $BACKUP_PATH"
if [ "$COMPRESS" = "true" ]; then
    echo "Compressed file: $BACKUP_PATH.tar.gz"
fi
echo ""
echo "To restore this backup, use:"
echo "  ./restore.sh --backup-path \"$BACKUP_PATH\""
echo ""

