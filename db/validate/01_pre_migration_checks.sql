-- Pre-Migration Validation Checks
-- Run these checks BEFORE applying schema changes to verify current state
-- All checks should pass before proceeding with migration

-- ============================================================================
-- 1. DATA INTEGRITY CHECKS
-- ============================================================================

-- Check for orphaned facility records (facilities without valid company)
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility f
    LEFT JOIN company c ON f.company_id = c.company_id
    WHERE f.company_id IS NOT NULL AND c.company_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility records (company_id references non-existent company)', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility records';
END $$;

-- Check for orphaned facility records (facilities without valid facility_type)
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility f
    LEFT JOIN facility_type ft ON f.facility_type_id = ft.facility_type_id
    WHERE f.facility_type_id IS NOT NULL AND ft.facility_type_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility records (facility_type_id references non-existent facility_type)', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_type references';
END $$;

-- Check for orphaned facility_contact records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility_contact fc
    LEFT JOIN facility f ON fc.facility_id = f.facility_id
    WHERE f.facility_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility_contact records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_contact records';
END $$;

-- Check for orphaned facility_service records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility_service fs
    LEFT JOIN facility f ON fs.facility_id = f.facility_id
    LEFT JOIN service_type st ON fs.service_type_id = st.service_type_id
    WHERE f.facility_id IS NULL OR st.service_type_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility_service records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_service records';
END $$;

-- Check for orphaned facility_product records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility_product fp
    LEFT JOIN facility f ON fp.facility_id = f.facility_id
    LEFT JOIN product p ON fp.product_id = p.product_id
    WHERE f.facility_id IS NULL OR p.product_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility_product records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_product records';
END $$;

-- Check for orphaned facility_transport_mode records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility_transport_mode ftm
    LEFT JOIN facility f ON ftm.facility_id = f.facility_id
    LEFT JOIN transport_mode tm ON ftm.transport_mode_id = tm.transport_mode_id
    WHERE f.facility_id IS NULL OR tm.transport_mode_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned facility_transport_mode records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_transport_mode records';
END $$;

-- Check for orphaned crop_acres records (if crop data tables exist)
DO $$
DECLARE
    table_exists BOOLEAN;
    orphaned_count INTEGER;
BEGIN
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'crop_acres'
    ) INTO table_exists;
    
    IF table_exists THEN
        SELECT COUNT(*) INTO orphaned_count
        FROM crop_acres ca
        LEFT JOIN region r ON ca.region_id = r.region_id
        LEFT JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
        WHERE r.region_id IS NULL OR ct.crop_type_id IS NULL;
        
        IF orphaned_count > 0 THEN
            RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % orphaned crop_acres records', orphaned_count;
        END IF;
        
        RAISE NOTICE 'PASS: No orphaned crop_acres records';
    END IF;
END $$;

-- ============================================================================
-- 2. DATA TYPE AND CONSTRAINT CHECKS
-- ============================================================================

-- Verify facility geometry is valid (if geom exists)
DO $$
DECLARE
    invalid_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO invalid_count
    FROM facility
    WHERE geom IS NOT NULL AND NOT ST_IsValid(geom);
    
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % facilities with invalid geometry', invalid_count;
    END IF;
    
    RAISE NOTICE 'PASS: All facility geometries are valid';
END $$;

-- Verify facility lat/lon are within valid range
DO $$
DECLARE
    invalid_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO invalid_count
    FROM facility
    WHERE latitude < -90 OR latitude > 90 
       OR longitude < -180 OR longitude > 180;
    
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found % facilities with invalid lat/lon coordinates', invalid_count;
    END IF;
    
    RAISE NOTICE 'PASS: All facility coordinates are valid';
END $$;

-- Verify unique constraints are maintained
DO $$
DECLARE
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT company_id, COUNT(*) as cnt
        FROM company
        GROUP BY company_id
        HAVING COUNT(*) > 1
    ) duplicates;
    
    IF duplicate_count > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Found duplicate company_id values';
    END IF;
    
    RAISE NOTICE 'PASS: Unique constraints are maintained';
END $$;

-- ============================================================================
-- 3. INDEX INTEGRITY CHECKS
-- ============================================================================

-- Verify critical indexes exist
DO $$
DECLARE
    missing_indexes TEXT[];
BEGIN
    SELECT ARRAY_AGG(indexname) INTO missing_indexes
    FROM (
        SELECT 'facility_geom_gix' AS indexname
        UNION ALL SELECT 'parcels_geom_gix'
        UNION ALL SELECT 'parcels_parcelnumb_uidx'
    ) expected
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND indexname = expected.indexname
    );
    
    IF missing_indexes IS NOT NULL AND array_length(missing_indexes, 1) > 0 THEN
        RAISE WARNING 'PRE-MIGRATION WARNING: Missing indexes: %', array_to_string(missing_indexes, ', ');
    ELSE
        RAISE NOTICE 'PASS: Critical indexes exist';
    END IF;
END $$;

-- ============================================================================
-- 4. VIEW INTEGRITY CHECKS
-- ============================================================================

-- Verify views can be queried (no broken dependencies)
DO $$
DECLARE
    broken_views TEXT[];
    view_name TEXT;
BEGIN
    broken_views := ARRAY[]::TEXT[];
    
    -- Check facility_with_names view
    BEGIN
        PERFORM * FROM facility_with_names LIMIT 1;
    EXCEPTION WHEN OTHERS THEN
        broken_views := array_append(broken_views, 'facility_with_names');
    END;
    
    -- Check parcel views if they exist
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'facility_parcels_8mi') THEN
        BEGIN
            PERFORM * FROM facility_parcels_8mi LIMIT 1;
        EXCEPTION WHEN OTHERS THEN
            broken_views := array_append(broken_views, 'facility_parcels_8mi');
        END;
    END IF;
    
    IF array_length(broken_views, 1) > 0 THEN
        RAISE EXCEPTION 'PRE-MIGRATION CHECK FAILED: Broken views: %', array_to_string(broken_views, ', ');
    END IF;
    
    RAISE NOTICE 'PASS: All views are queryable';
END $$;

-- ============================================================================
-- 5. RECORD COUNT BASELINE
-- ============================================================================

-- Store baseline record counts for comparison after migration
CREATE TABLE IF NOT EXISTS migration_baseline (
    check_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    table_name TEXT,
    record_count BIGINT,
    PRIMARY KEY (check_date, table_name)
);

-- Clear old baselines (keep only most recent)
DELETE FROM migration_baseline 
WHERE check_date < (SELECT MAX(check_date) FROM migration_baseline);

-- Record current counts
INSERT INTO migration_baseline (table_name, record_count)
SELECT 'company', COUNT(*) FROM company
UNION ALL SELECT 'facility', COUNT(*) FROM facility
UNION ALL SELECT 'facility_contact', COUNT(*) FROM facility_contact
UNION ALL SELECT 'facility_service', COUNT(*) FROM facility_service
UNION ALL SELECT 'facility_product', COUNT(*) FROM facility_product
UNION ALL SELECT 'facility_transport_mode', COUNT(*) FROM facility_transport_mode
UNION ALL SELECT 'parcels', COUNT(*) FROM parcels WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'parcels')
UNION ALL SELECT 'crop_acres', COUNT(*) FROM crop_acres WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'crop_acres')
ON CONFLICT (check_date, table_name) DO NOTHING;

RAISE NOTICE 'PASS: Baseline record counts recorded';

-- ============================================================================
-- SUMMARY
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'PRE-MIGRATION CHECKS COMPLETED';
    RAISE NOTICE 'All validation checks passed';
    RAISE NOTICE 'Safe to proceed with migration';
    RAISE NOTICE '========================================';
END $$;

