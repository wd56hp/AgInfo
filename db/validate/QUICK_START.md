# Quick Start: Migration Validation

## Quick Reference

### Before Any Schema Change

```bash
# Run pre-migration checks
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/01_pre_migration_checks.sql
```

**If checks pass**: Proceed with migration  
**If checks fail**: Fix issues before proceeding

### After Schema Change

```bash
# Run post-migration checks
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/02_post_migration_checks.sql
```

**If checks pass**: Migration successful  
**If checks fail**: Review errors and restore from backup if needed

### Automated (Recommended)

**Linux/Mac:**
```bash
./db/validate/validate_migration.sh db/init/08_schema_crop_data.sql
```

**Windows (PowerShell):**
```powershell
.\db\validate\validate_migration.ps1 -MigrationFile "db\init\08_schema_crop_data.sql"
```

This automatically:
1. Runs pre-migration checks
2. Creates a backup
3. Applies the migration
4. Runs post-migration checks

## What to Look For

### ✅ Success Messages
- `PASS: No orphaned records`
- `PASS: All geometries are valid`
- `PASS: Record counts match baseline`

### ⚠️ Warnings (Review but may be OK)
- Record count differences (if expected)
- Missing optional indexes

### ❌ Errors (Must Fix)
- `CHECK FAILED: Found orphaned records`
- `CHECK FAILED: Broken views`
- `CHECK FAILED: Invalid geometry`

## Common Issues

### Orphaned Records
**Problem**: Foreign key references point to non-existent records

**Solution**: 
```sql
-- Find orphaned records
SELECT * FROM facility f
LEFT JOIN company c ON f.company_id = c.company_id
WHERE f.company_id IS NOT NULL AND c.company_id IS NULL;

-- Fix: Update or delete orphaned records
UPDATE facility SET company_id = NULL WHERE company_id NOT IN (SELECT company_id FROM company);
```

### Broken Views
**Problem**: View depends on table/column that was changed

**Solution**: Recreate the view
```sql
-- Check view definition
SELECT pg_get_viewdef('facility_with_names', true);

-- Recreate if needed
CREATE OR REPLACE VIEW facility_with_names AS ...;
```

### Geometry Errors
**Problem**: Invalid geometry after migration

**Solution**:
```sql
-- Find invalid geometries
SELECT facility_id, ST_IsValidReason(geom) 
FROM facility 
WHERE NOT ST_IsValid(geom);

-- Fix invalid geometries
UPDATE facility 
SET geom = ST_MakeValid(geom) 
WHERE NOT ST_IsValid(geom);
```

## Need Help?

See full documentation: `db/validate/README.md`

