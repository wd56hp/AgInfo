# Database Migration Validation

This directory contains validation scripts to ensure database schema changes don't corrupt existing data in production.

## Overview

The validation system provides:
- **Pre-migration checks**: Validates current database state before changes
- **Post-migration checks**: Verifies data integrity after schema changes
- **Automated workflow**: Scripts to run checks and migrations safely

## Files

### Validation Scripts

- **`01_pre_migration_checks.sql`**: Runs before migration to:
  - Check for orphaned records (broken foreign keys)
  - Validate data types and constraints
  - Verify index integrity
  - Test view functionality
  - Record baseline record counts

- **`02_post_migration_checks.sql`**: Runs after migration to:
  - Compare record counts with baseline
  - Re-validate all integrity checks
  - Verify constraints are intact
  - Test geometry validity
  - Confirm views still work

### Automation Scripts

- **`validate_migration.sh`**: Bash script for Linux/Mac
- **`validate_migration.ps1`**: PowerShell script for Windows

## Usage

### Manual Validation

#### Step 1: Pre-Migration Checks

```bash
# Linux/Mac
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/01_pre_migration_checks.sql

# Windows (PowerShell)
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/01_pre_migration_checks.sql
```

#### Step 2: Apply Migration

```bash
# Apply your migration file
docker exec -i aginfo-postgis psql -U agadmin -d aginfo < db/init/08_schema_crop_data.sql
```

#### Step 3: Post-Migration Checks

```bash
# Linux/Mac
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/02_post_migration_checks.sql

# Windows (PowerShell)
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/02_post_migration_checks.sql
```

### Automated Validation

#### Linux/Mac

```bash
# Make script executable
chmod +x db/validate/validate_migration.sh

# Run validation with migration
./db/validate/validate_migration.sh db/init/08_schema_crop_data.sql
```

#### Windows (PowerShell)

```powershell
# Run validation with migration
.\db\validate\validate_migration.ps1 -MigrationFile "db\init\08_schema_crop_data.sql"
```

## What Gets Checked

### Pre-Migration Checks

1. **Data Integrity**
   - Orphaned facility records (invalid company_id)
   - Orphaned facility_type references
   - Orphaned junction table records (facility_service, facility_product, etc.)
   - Orphaned crop_acres records (if applicable)

2. **Data Validation**
   - Facility geometry validity
   - Coordinate range validation (lat/lon)
   - Unique constraint integrity

3. **Index Integrity**
   - Critical indexes exist (spatial indexes, unique indexes)

4. **View Integrity**
   - All views are queryable
   - No broken dependencies

5. **Baseline Recording**
   - Record counts for all tables stored for comparison

### Post-Migration Checks

1. **Record Count Comparison**
   - Compares current counts with pre-migration baseline
   - Warns if counts changed unexpectedly

2. **Re-validation**
   - Re-runs all pre-migration integrity checks
   - Verifies no data was corrupted

3. **Constraint Validation**
   - Foreign key constraints still exist
   - Unique constraints maintained

4. **Geometry Validation**
   - All geometries still valid
   - Coordinate consistency

5. **View Validation**
   - All views still queryable
   - No broken dependencies

6. **Index Validation**
   - Critical indexes still exist

## Integration with Docker

To use these scripts with your Docker setup, you need to mount the validate directory:

```yaml
# In docker-compose.yml, add to postgis service volumes:
volumes:
  - ./db/validate:/tmp/validate:ro
```

Or copy the files into the container:

```bash
docker cp db/validate aginfo-postgis:/tmp/validate
```

## Best Practices

1. **Always run pre-migration checks first**
   - Don't proceed if checks fail
   - Fix issues before migrating

2. **Create backups before migration**
   - The automated scripts create backups automatically
   - Keep backups until post-migration checks pass

3. **Review warnings carefully**
   - Some warnings may be expected (e.g., new tables)
   - Errors should be investigated before proceeding

4. **Run in staging first**
   - Test migrations on a copy of production data
   - Verify all checks pass before production

5. **Monitor record counts**
   - Unexpected count changes may indicate data loss
   - Investigate any discrepancies

## Customizing Checks

You can add custom validation checks by editing the SQL files:

```sql
-- Add to 01_pre_migration_checks.sql or 02_post_migration_checks.sql

DO $$
DECLARE
    custom_check_result INTEGER;
BEGIN
    -- Your custom validation logic
    SELECT COUNT(*) INTO custom_check_result
    FROM your_table
    WHERE your_condition;
    
    IF custom_check_result > 0 THEN
        RAISE EXCEPTION 'Custom check failed: %', custom_check_result;
    END IF;
    
    RAISE NOTICE 'PASS: Custom check';
END $$;
```

## Troubleshooting

### Checks Fail with Orphaned Records

If you see orphaned record errors:
1. Identify the orphaned records
2. Decide: delete them, fix references, or keep them
3. Fix before proceeding with migration

### Record Count Mismatches

If post-migration shows count differences:
1. Check if differences are expected (new data, deletions)
2. Verify no data was accidentally deleted
3. Review migration script for issues

### View Errors

If views fail to query:
1. Check view dependencies (tables, columns)
2. Verify migration didn't break view definitions
3. Recreate views if necessary

## Example Output

### Successful Pre-Migration

```
NOTICE:  PASS: No orphaned facility records
NOTICE:  PASS: No orphaned facility_type references
NOTICE:  PASS: All facility geometries are valid
NOTICE:  PASS: All views are queryable
NOTICE:  PASS: Baseline record counts recorded
NOTICE:  ========================================
NOTICE:  PRE-MIGRATION CHECKS COMPLETED
NOTICE:  All validation checks passed
NOTICE:  Safe to proceed with migration
NOTICE:  ========================================
```

### Failed Check

```
ERROR:  PRE-MIGRATION CHECK FAILED: Found 5 orphaned facility records (company_id references non-existent company)
```

## Related Documentation

- Main database schema: `db/README.md`
- Migration scripts: `db/init/`
- CDL import guide: `db/README_CDL_IMPORT.md`

