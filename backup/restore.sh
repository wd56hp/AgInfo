#!/bin/bash
# AgInfo Restore Script (Bash)
# Restores a backup of database and application data

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Setup logging
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/restore_$TIMESTAMP.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local level="${2:-INFO}"
    local message="[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $1"
    echo "$message" | tee -a "$LOG_FILE"
}

# Default values
SKIP_GEOSERVER=false
SKIP_WEB=false
SKIP_DATABASE=false
FORCE=false

# Parse command line arguments
BACKUP_PATH=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-path)
            BACKUP_PATH="$2"
            shift 2
            ;;
        --skip-geoserver)
            SKIP_GEOSERVER=true
            shift
            ;;
        --skip-web)
            SKIP_WEB=true
            shift
            ;;
        --skip-database)
            SKIP_DATABASE=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --backup-path PATH [--skip-geoserver] [--skip-web] [--skip-database] [--force]"
            exit 1
            ;;
    esac
done

if [ -z "$BACKUP_PATH" ]; then
    log "ERROR: --backup-path is required" "ERROR"
    echo "Usage: $0 --backup-path PATH [options]"
    exit 1
fi

log "========================================"
log "AgInfo Restore Script"
log "========================================"
log "Backup Path: $BACKUP_PATH"
log "Log File: $LOG_FILE"
log ""

# Check if backup path exists
if [ ! -d "$BACKUP_PATH" ]; then
    # Try with .tar.gz extension
    if [ -f "$BACKUP_PATH.tar.gz" ]; then
        log "Found compressed backup, extracting..." "INFO"
        EXTRACT_DIR=$(dirname "$BACKUP_PATH")
        tar -xzf "$BACKUP_PATH.tar.gz" -C "$EXTRACT_DIR"
        log "✓ Extraction complete" "INFO"
    else
        log "ERROR: Backup path not found: $BACKUP_PATH" "ERROR"
        exit 1
    fi
fi

# Check for manifest
MANIFEST_PATH="$BACKUP_PATH/manifest.json"
if [ ! -f "$MANIFEST_PATH" ]; then
    log "WARNING: Manifest file not found. Proceeding with restore anyway..." "WARN"
else
    log "Backup Information:" "INFO"
    log "  Date: $(jq -r '.date' "$MANIFEST_PATH" 2>/dev/null || echo 'N/A')" "INFO"
    log "  Timestamp: $(jq -r '.timestamp' "$MANIFEST_PATH" 2>/dev/null || echo 'N/A')" "INFO"
    log ""
fi

# Confirm restore
if [ "$FORCE" != "true" ]; then
    log "WARNING: This will overwrite existing data!" "WARN"
    read -p "Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
        log "Restore cancelled." "INFO"
        exit 0
    fi
fi

# Restore Database
if [ "$SKIP_DATABASE" != "true" ]; then
    log ""
    log "Restoring PostgreSQL database..." "INFO"
    
    # Check if container is running
    if ! docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | grep -q "aginfo-postgis"; then
        log "ERROR: PostGIS container is not running. Please start it first." "ERROR"
        log "  Run: docker-compose up -d postgis" "INFO"
        exit 1
    fi
    
    DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.dump"
    if [ ! -f "$DUMP_FILE" ]; then
        DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.sql"
    fi
    
    if [ ! -f "$DUMP_FILE" ]; then
        log "  ✗ Database backup file not found: $DUMP_FILE" "ERROR"
    else
        # Get database credentials
        DB_NAME="${POSTGRES_DB:-aginfo}"
        DB_USER="${POSTGRES_USER:-agadmin}"
        
        log "  Copying dump file to container..." "INFO"
        docker cp "$DUMP_FILE" aginfo-postgis:/tmp/aginfo_restore.dump
        
        log "  Dropping existing database connections..." "INFO"
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
        
        log "  Dropping and recreating database..." "INFO"
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" >/dev/null 2>&1 || true
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" >/dev/null 2>&1
        
        log "  Restoring database from backup..." "INFO"
        if docker exec aginfo-postgis pg_restore -U "$DB_USER" -d "$DB_NAME" -F c /tmp/aginfo_restore.dump 2>&1 | tee -a "$LOG_FILE"; then
            docker exec aginfo-postgis rm /tmp/aginfo_restore.dump
            log "  ✓ Database restore complete" "INFO"
        else
            log "  ✗ Database restore failed" "ERROR"
            log "  Continuing with other restores..." "WARN"
        fi
    fi
else
    log ""
    log "Skipping database restore (--skip-database flag)" "INFO"
fi

# Restore GeoServer data
if [ "$SKIP_GEOSERVER" != "true" ]; then
    log ""
    log "Restoring GeoServer data..." "INFO"
    GEOSERVER_BACKUP="$BACKUP_PATH/geoserver/data_dir"
    GEOSERVER_DEST="$PROJECT_ROOT/geoserver/data_dir"
    
    if [ -d "$GEOSERVER_BACKUP" ]; then
        log "  Restoring GeoServer data directory..." "INFO"
        if [ -d "$GEOSERVER_DEST" ]; then
            rm -rf "$GEOSERVER_DEST"
        fi
        cp -r "$GEOSERVER_BACKUP" "$GEOSERVER_DEST"
        log "  ✓ GeoServer data restore complete" "INFO"
        log "  NOTE: You may need to restart the GeoServer container" "WARN"
    else
        log "  ⚠ GeoServer backup not found, skipping..." "WARN"
    fi
else
    log ""
    log "Skipping GeoServer restore (--skip-geoserver flag)" "INFO"
fi

# Restore Web files
if [ "$SKIP_WEB" != "true" ]; then
    log ""
    log "Restoring web files..." "INFO"
    WEB_BACKUP="$BACKUP_PATH/web"
    WEB_DEST="$PROJECT_ROOT/web"
    
    if [ -d "$WEB_BACKUP" ]; then
        log "  Restoring web directory..." "INFO"
        if [ -d "$WEB_DEST" ]; then
            rm -rf "$WEB_DEST"
        fi
        cp -r "$WEB_BACKUP" "$WEB_DEST"
        log "  ✓ Web files restore complete" "INFO"
    else
        log "  ⚠ Web backup not found, skipping..." "WARN"
    fi
else
    log ""
    log "Skipping web files restore (--skip-web flag)" "INFO"
fi

# Restore Django static and media files
log ""
log "Restoring Django files..." "INFO"
DJANGO_BACKUP="$BACKUP_PATH/django"
DJANGO_STATIC_DEST="$PROJECT_ROOT/aginfo_django/staticfiles"
DJANGO_MEDIA_DEST="$PROJECT_ROOT/aginfo_django/media"

if [ -d "$DJANGO_BACKUP/staticfiles" ]; then
    log "  Restoring Django static files..." "INFO"
    if [ -d "$DJANGO_STATIC_DEST" ]; then
        rm -rf "$DJANGO_STATIC_DEST"
    fi
    cp -r "$DJANGO_BACKUP/staticfiles" "$DJANGO_STATIC_DEST"
fi

if [ -d "$DJANGO_BACKUP/media" ]; then
    log "  Restoring Django media files..." "INFO"
    if [ -d "$DJANGO_MEDIA_DEST" ]; then
        rm -rf "$DJANGO_MEDIA_DEST"
    fi
    cp -r "$DJANGO_BACKUP/media" "$DJANGO_MEDIA_DEST"
fi

if [ -d "$DJANGO_BACKUP/staticfiles" ] || [ -d "$DJANGO_BACKUP/media" ]; then
    log "  ✓ Django files restore complete" "INFO"
else
    log "  ⚠ Django backup not found, skipping..." "WARN"
fi

# Restore configuration files (optional, with warning)
log ""
log "Configuration files restore..." "INFO"
CONFIG_BACKUP="$BACKUP_PATH/config"
if [ -d "$CONFIG_BACKUP" ]; then
    log "  Configuration files are available in: $CONFIG_BACKUP" "INFO"
    log "  Review and manually restore .env and other config files if needed" "WARN"
    log "  WARNING: Do not overwrite .env without reviewing changes!" "WARN"
else
    log "  ⚠ Configuration backup not found" "WARN"
fi

# Summary
log ""
log "========================================"
log "Restore Complete!" "INFO"
log "========================================"
log ""
log "Next steps:" "INFO"
log "  1. Review restored configuration files if needed" "INFO"
log "  2. Restart containers: docker-compose restart" "INFO"
log "  3. Verify the application is working correctly" "INFO"
log ""
