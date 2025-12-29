#!/bin/bash
# AgInfo Restore Script (Bash)
# Restores a backup of database and application data

set -e

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
    echo "ERROR: --backup-path is required"
    echo "Usage: $0 --backup-path PATH [options]"
    exit 1
fi

echo "========================================"
echo "AgInfo Restore Script"
echo "========================================"
echo "Backup Path: $BACKUP_PATH"
echo ""

# Check if backup path exists
if [ ! -d "$BACKUP_PATH" ]; then
    # Try with .tar.gz extension
    if [ -f "$BACKUP_PATH.tar.gz" ]; then
        echo "Found compressed backup, extracting..."
        EXTRACT_DIR=$(dirname "$BACKUP_PATH")
        tar -xzf "$BACKUP_PATH.tar.gz" -C "$EXTRACT_DIR"
        echo "✓ Extraction complete"
    else
        echo "ERROR: Backup path not found: $BACKUP_PATH"
        exit 1
    fi
fi

# Check for manifest
MANIFEST_PATH="$BACKUP_PATH/manifest.json"
if [ ! -f "$MANIFEST_PATH" ]; then
    echo "WARNING: Manifest file not found. Proceeding with restore anyway..."
else
    echo "Backup Information:"
    echo "  Date: $(jq -r '.date' "$MANIFEST_PATH" 2>/dev/null || echo 'N/A')"
    echo "  Timestamp: $(jq -r '.timestamp' "$MANIFEST_PATH" 2>/dev/null || echo 'N/A')"
    echo ""
fi

# Confirm restore
if [ "$FORCE" != "true" ]; then
    echo "WARNING: This will overwrite existing data!"
    read -p "Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi
fi

# Restore Database
if [ "$SKIP_DATABASE" != "true" ]; then
    echo ""
    echo "Restoring PostgreSQL database..."
    
    # Check if container is running
    if ! docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | grep -q "aginfo-postgis"; then
        echo "ERROR: PostGIS container is not running. Please start it first."
        echo "  Run: docker-compose up -d postgis"
        exit 1
    fi
    
    DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.dump"
    if [ ! -f "$DUMP_FILE" ]; then
        DUMP_FILE="$BACKUP_PATH/database/aginfo_backup.sql"
    fi
    
    if [ ! -f "$DUMP_FILE" ]; then
        echo "  ✗ Database backup file not found: $DUMP_FILE"
    else
        # Get database credentials
        DB_NAME="${POSTGRES_DB:-aginfo}"
        DB_USER="${POSTGRES_USER:-agadmin}"
        
        echo "  Copying dump file to container..."
        docker cp "$DUMP_FILE" aginfo-postgis:/tmp/aginfo_restore.dump
        
        echo "  Dropping existing database connections..."
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
        
        echo "  Dropping and recreating database..."
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" >/dev/null 2>&1 || true
        docker exec aginfo-postgis psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" >/dev/null 2>&1
        
        echo "  Restoring database from backup..."
        if docker exec aginfo-postgis pg_restore -U "$DB_USER" -d "$DB_NAME" -F c /tmp/aginfo_restore.dump >/dev/null 2>&1; then
            docker exec aginfo-postgis rm /tmp/aginfo_restore.dump
            echo "  ✓ Database restore complete"
        else
            echo "  ✗ Database restore failed"
            echo "  Continuing with other restores..."
        fi
    fi
else
    echo ""
    echo "Skipping database restore (--skip-database flag)"
fi

# Restore GeoServer data
if [ "$SKIP_GEOSERVER" != "true" ]; then
    echo ""
    echo "Restoring GeoServer data..."
    GEOSERVER_BACKUP="$BACKUP_PATH/geoserver/data_dir"
    GEOSERVER_DEST="geoserver/data_dir"
    
    if [ -d "$GEOSERVER_BACKUP" ]; then
        echo "  Restoring GeoServer data directory..."
        if [ -d "$GEOSERVER_DEST" ]; then
            rm -rf "$GEOSERVER_DEST"
        fi
        cp -r "$GEOSERVER_BACKUP" "$GEOSERVER_DEST"
        echo "  ✓ GeoServer data restore complete"
        echo "  NOTE: You may need to restart the GeoServer container"
    else
        echo "  ⚠ GeoServer backup not found, skipping..."
    fi
else
    echo ""
    echo "Skipping GeoServer restore (--skip-geoserver flag)"
fi

# Restore Web files
if [ "$SKIP_WEB" != "true" ]; then
    echo ""
    echo "Restoring web files..."
    WEB_BACKUP="$BACKUP_PATH/web"
    WEB_DEST="web"
    
    if [ -d "$WEB_BACKUP" ]; then
        echo "  Restoring web directory..."
        if [ -d "$WEB_DEST" ]; then
            rm -rf "$WEB_DEST"
        fi
        cp -r "$WEB_BACKUP" "$WEB_DEST"
        echo "  ✓ Web files restore complete"
    else
        echo "  ⚠ Web backup not found, skipping..."
    fi
else
    echo ""
    echo "Skipping web files restore (--skip-web flag)"
fi

# Restore Django static and media files
echo ""
echo "Restoring Django files..."
DJANGO_BACKUP="$BACKUP_PATH/django"
DJANGO_STATIC_DEST="aginfo_django/staticfiles"
DJANGO_MEDIA_DEST="aginfo_django/media"

if [ -d "$DJANGO_BACKUP/staticfiles" ]; then
    echo "  Restoring Django static files..."
    if [ -d "$DJANGO_STATIC_DEST" ]; then
        rm -rf "$DJANGO_STATIC_DEST"
    fi
    cp -r "$DJANGO_BACKUP/staticfiles" "$DJANGO_STATIC_DEST"
fi

if [ -d "$DJANGO_BACKUP/media" ]; then
    echo "  Restoring Django media files..."
    if [ -d "$DJANGO_MEDIA_DEST" ]; then
        rm -rf "$DJANGO_MEDIA_DEST"
    fi
    cp -r "$DJANGO_BACKUP/media" "$DJANGO_MEDIA_DEST"
fi

if [ -d "$DJANGO_BACKUP/staticfiles" ] || [ -d "$DJANGO_BACKUP/media" ]; then
    echo "  ✓ Django files restore complete"
else
    echo "  ⚠ Django backup not found, skipping..."
fi

# Restore configuration files (optional, with warning)
echo ""
echo "Configuration files restore..."
CONFIG_BACKUP="$BACKUP_PATH/config"
if [ -d "$CONFIG_BACKUP" ]; then
    echo "  Configuration files are available in: $CONFIG_BACKUP"
    echo "  Review and manually restore .env and other config files if needed"
    echo "  WARNING: Do not overwrite .env without reviewing changes!"
else
    echo "  ⚠ Configuration backup not found"
fi

# Summary
echo ""
echo "========================================"
echo "Restore Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Review restored configuration files if needed"
echo "  2. Restart containers: docker-compose restart"
echo "  3. Verify the application is working correctly"
echo ""

