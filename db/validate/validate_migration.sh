#!/bin/bash
# Migration Validation Script
# Runs pre-migration checks, applies migration, then post-migration checks

set -e  # Exit on error

DB_HOST="${DB_HOST:-172.16.101.20}"
DB_PORT="${DB_PORT:-15433}"
DB_NAME="${DB_NAME:-aginfo}"
DB_USER="${DB_USER:-agadmin}"
MIGRATION_FILE="${1:-}"

if [ -z "$MIGRATION_FILE" ]; then
    echo "Usage: $0 <migration_file.sql>"
    echo "Example: $0 ../init/08_schema_crop_data.sql"
    exit 1
fi

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

echo "=========================================="
echo "Migration Validation Process"
echo "=========================================="
echo "Database: $DB_NAME @ $DB_HOST:$DB_PORT"
echo "Migration file: $MIGRATION_FILE"
echo ""

# Step 1: Run pre-migration checks
echo "Step 1: Running pre-migration checks..."
docker exec aginfo-postgis psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/validate/01_pre_migration_checks.sql
if [ $? -ne 0 ]; then
    echo "ERROR: Pre-migration checks failed. Aborting migration."
    exit 1
fi
echo "✓ Pre-migration checks passed"
echo ""

# Step 2: Backup database (optional but recommended)
echo "Step 2: Creating backup..."
BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
docker exec aginfo-postgis pg_dump -U "$DB_USER" -d "$DB_NAME" > "$BACKUP_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Backup created: $BACKUP_FILE"
else
    echo "WARNING: Backup failed, but continuing..."
fi
echo ""

# Step 3: Apply migration
echo "Step 3: Applying migration..."
docker exec -i aginfo-postgis psql -U "$DB_USER" -d "$DB_NAME" < "$MIGRATION_FILE"
if [ $? -ne 0 ]; then
    echo "ERROR: Migration failed. Database may be in inconsistent state."
    echo "Consider restoring from backup: $BACKUP_FILE"
    exit 1
fi
echo "✓ Migration applied successfully"
echo ""

# Step 4: Run post-migration checks
echo "Step 4: Running post-migration checks..."
docker exec aginfo-postgis psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/validate/02_post_migration_checks.sql
if [ $? -ne 0 ]; then
    echo "ERROR: Post-migration checks failed. Review errors above."
    exit 1
fi
echo "✓ Post-migration checks passed"
echo ""

echo "=========================================="
echo "Migration completed successfully!"
echo "=========================================="

