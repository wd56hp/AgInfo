#!/bin/bash
# AgInfo Backup Script (Bash)
# Creates a complete backup of database and application data

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Setup logging
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/backup_$TIMESTAMP.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local message="$1"
    local level="${2:-INFO}"
    local log_message="[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $message"
    echo "$log_message" | tee -a "$LOG_FILE"
}

# Load .env file if it exists (from project root)
ENV_PATH="$PROJECT_ROOT/.env"
if [ -f "$ENV_PATH" ]; then
    log "Loading environment variables from .env file"
    # Temporarily disable exit on error for .env loading
    set +e
    # Use a safer method to load .env file, handling BOM and encoding issues
    # Remove BOM first, then process lines
    while IFS= read -r line || [ -n "$line" ]; do
        # Remove BOM and carriage returns, skip lines starting with invalid characters
        line=$(echo "$line" | sed '1s/^\xEF\xBB\xBF//' | tr -d '\r')
        # Skip if line starts with # (comment) or is empty
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue
        # Check if line contains = and doesn't start with special characters
        [[ "$line" != *"="* ]] && continue
        [[ "$line" =~ ^[^a-zA-Z_] ]] && continue
        # Extract key and value
        key="${line%%=*}"
        value="${line#*=}"
        # Remove leading/trailing whitespace
        key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/^["'\'']//;s/["'\'']$//')
        # Export if key is valid (alphanumeric and underscore only)
        if [[ -n "$key" ]] && [[ "$key" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
            export "$key=$value" 2>/dev/null || true
        fi
    done < <(sed '1s/^\xEF\xBB\xBF//' "$ENV_PATH" 2>/dev/null || cat "$ENV_PATH")
    set -e
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
BACKUP_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="$BACKUP_DIR/aginfo_backup_$BACKUP_TIMESTAMP"

log "========================================"
log "AgInfo Backup Script"
log "========================================"
log "Backup Directory: $BACKUP_PATH"
log "Log File: $LOG_FILE"
log ""

# Create backup directory structure
log "Creating backup directory structure..."
mkdir -p "$BACKUP_PATH"/{database,geoserver,web,django,config}
log "Backup directories created"

# Check if Docker containers are running
log "Checking Docker containers..."
POSTGIS_RUNNING=$(docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | grep -q "aginfo-postgis" && echo "yes" || echo "no")
GEOSERVER_RUNNING=$(docker ps --filter "name=aginfo-geoserver" --format "{{.Names}}" | grep -q "aginfo-geoserver" && echo "yes" || echo "no")

if [ "$POSTGIS_RUNNING" != "yes" ]; then
    log "WARNING: PostGIS container is not running. Database backup may fail." "WARN"
fi

# Backup Database
log ""
log "Backing up PostgreSQL database..."
# Get database credentials from environment or use defaults
DB_NAME="${POSTGRES_DB:-aginfo}"
DB_USER="${POSTGRES_USER:-agadmin}"
DB_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
DB_HOST="${POSTGIS_HOST_PORT:-localhost:15433}"

DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.dump"

log "  Exporting database to: $DUMP_FILE"
if docker exec aginfo-postgis pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -f /tmp/aginfo_backup.dump 2>&1 | tee -a "$LOG_FILE"; then
    docker cp aginfo-postgis:/tmp/aginfo_backup.dump "$DUMP_FILE"
    docker exec aginfo-postgis rm /tmp/aginfo_backup.dump
    
    DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    log "  ✓ Database backup complete ($DUMP_SIZE)"
else
    log "  ✗ Database backup failed" "ERROR"
    log "  Continuing with other backups..." "WARN"
fi

# Backup GeoServer data
if [ "$SKIP_GEOSERVER" != "true" ]; then
    log ""
    log "Backing up GeoServer data..."
    GEOSERVER_SOURCE="$PROJECT_ROOT/geoserver/data_dir"
    if [ -d "$GEOSERVER_SOURCE" ]; then
        log "  Copying GeoServer data directory..."
        cp -r "$GEOSERVER_SOURCE" "$BACKUP_PATH/geoserver/"
        
        GEOSERVER_SIZE=$(du -sh "$BACKUP_PATH/geoserver/data_dir" | cut -f1)
        log "  ✓ GeoServer backup complete ($GEOSERVER_SIZE)"
    else
        log "  ⚠ GeoServer data directory not found, skipping..." "WARN"
    fi
else
    log ""
    log "Skipping GeoServer backup (--skip-geoserver flag)"
fi

# Backup Web files
if [ "$SKIP_WEB" != "true" ]; then
    log ""
    log "Backing up web files..."
    WEB_SOURCE="$PROJECT_ROOT/web"
    if [ -d "$WEB_SOURCE" ]; then
        log "  Copying web directory..."
        cp -r "$WEB_SOURCE" "$BACKUP_PATH/"
        
        WEB_SIZE=$(du -sh "$BACKUP_PATH/web" | cut -f1)
        log "  ✓ Web files backup complete ($WEB_SIZE)"
    else
        log "  ⚠ Web directory not found, skipping..." "WARN"
    fi
else
    log ""
    log "Skipping web files backup (--skip-web flag)"
fi

# Backup Django static and media files
log ""
log "Backing up Django files..."
DJANGO_STATIC="$PROJECT_ROOT/aginfo_django/staticfiles"
DJANGO_MEDIA="$PROJECT_ROOT/aginfo_django/media"

if [ -d "$DJANGO_STATIC" ]; then
    log "  Copying Django static files..."
    cp -r "$DJANGO_STATIC" "$BACKUP_PATH/django/"
fi

if [ -d "$DJANGO_MEDIA" ]; then
    log "  Copying Django media files..."
    cp -r "$DJANGO_MEDIA" "$BACKUP_PATH/django/"
fi

if [ -d "$DJANGO_STATIC" ] || [ -d "$DJANGO_MEDIA" ]; then
    log "  ✓ Django files backup complete"
else
    log "  ⚠ Django static/media directories not found, skipping..." "WARN"
fi

# Backup configuration files
log ""
log "Backing up configuration files..."
CONFIG_DEST="$BACKUP_PATH/config"

# Backup .env files (if they exist)
if [ -f "$ENV_PATH" ]; then
    cp "$ENV_PATH" "$CONFIG_DEST/.env"
    log "  ✓ .env file backed up"
fi

# Backup docker-compose.yml
DOCKER_COMPOSE_PATH="$PROJECT_ROOT/docker-compose.yml"
if [ -f "$DOCKER_COMPOSE_PATH" ]; then
    cp "$DOCKER_COMPOSE_PATH" "$CONFIG_DEST/docker-compose.yml"
fi

# Backup Django settings (for reference)
SETTINGS_PATH="$PROJECT_ROOT/aginfo_django/settings.py"
if [ -f "$SETTINGS_PATH" ]; then
    cp "$SETTINGS_PATH" "$CONFIG_DEST/settings.py"
fi

log "  ✓ Configuration files backed up"

# Create backup manifest
log ""
log "Creating backup manifest..."
cat > "$BACKUP_PATH/manifest.json" <<EOF
{
  "timestamp": "$BACKUP_TIMESTAMP",
  "date": "$(date +"%Y-%m-%d %H:%M:%S")",
  "backup_path": "$BACKUP_PATH",
  "log_file": "$LOG_FILE",
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
log "  ✓ Manifest created"

# Compress backup if requested
if [ "$COMPRESS" = "true" ]; then
    log ""
    log "Compressing backup..."
    ZIP_FILE="$BACKUP_PATH.tar.gz"
    tar -czf "$ZIP_FILE" -C "$BACKUP_DIR" "aginfo_backup_$BACKUP_TIMESTAMP"
    
    ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
    log "  ✓ Backup compressed ($ZIP_SIZE)"
    
    # Optionally remove uncompressed backup
    log "  Removing uncompressed backup..."
    rm -rf "$BACKUP_PATH"
    log "  ✓ Compression complete"
fi

# Summary
log ""
log "========================================"
log "Backup Complete!"
log "========================================"
log "Backup location: $BACKUP_PATH"
log "Log file: $LOG_FILE"
if [ "$COMPRESS" = "true" ]; then
    log "Compressed file: $BACKUP_PATH.tar.gz"
fi
log ""
log "To restore this backup, use:"
log "  ./backup/restore.sh --backup-path \"$BACKUP_PATH\""
log ""
