-- Post-Migration Validation Checks
-- Run these checks AFTER applying schema changes to verify data integrity
-- Compares current state against pre-migration baseline

-- ============================================================================
-- 1. RECORD COUNT VALIDATION
-- ============================================================================

-- Compare record counts with baseline
DO $$
DECLARE
    baseline_record migration_baseline%ROWTYPE;
    current_count BIGINT;
    table_list TEXT[] := ARRAY['company', 'facility', 'facility_contact', 'facility_service', 'facility_product', 'facility_transport_mode'];
    table_name TEXT;
    differences TEXT[] := ARRAY[]::TEXT[];
BEGIN
    -- Get most recent baseline
    FOR table_name IN SELECT unnest(table_list)
    LOOP
        SELECT * INTO baseline_record
        FROM migration_baseline
        WHERE table_name = table_name
        ORDER BY check_date DESC
        LIMIT 1;
        
        IF baseline_record.table_name IS NOT NULL THEN
            -- Get current count
            EXECUTE format('SELECT COUNT(*) FROM %I', table_name) INTO current_count;
            
            -- Compare
            IF current_count != baseline_record.record_count THEN
                differences := array_append(differences, 
                    format('%s: baseline=%s, current=%s (diff=%s)', 
                        table_name, 
                        baseline_record.record_count, 
                        current_count,
                        current_count - baseline_record.record_count));
            END IF;
        END IF;
    END LOOP;
    
    -- Check parcels if table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'parcels') THEN
        SELECT * INTO baseline_record
        FROM migration_baseline
        WHERE table_name = 'parcels'
        ORDER BY check_date DESC
        LIMIT 1;
        
        IF baseline_record.table_name IS NOT NULL THEN
            SELECT COUNT(*) INTO current_count FROM parcels;
            IF current_count != baseline_record.record_count THEN
                differences := array_append(differences, 
                    format('parcels: baseline=%s, current=%s (diff=%s)', 
                        baseline_record.record_count, 
                        current_count,
                        current_count - baseline_record.record_count));
            END IF;
        END IF;
    END IF;
    
    -- Check crop_acres if table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'crop_acres') THEN
        SELECT * INTO baseline_record
        FROM migration_baseline
        WHERE table_name = 'crop_acres'
        ORDER BY check_date DESC
        LIMIT 1;
        
        IF baseline_record.table_name IS NOT NULL THEN
            SELECT COUNT(*) INTO current_count FROM crop_acres;
            IF current_count != baseline_record.record_count THEN
                differences := array_append(differences, 
                    format('crop_acres: baseline=%s, current=%s (diff=%s)', 
                        baseline_record.record_count, 
                        current_count,
                        current_count - baseline_record.record_count));
            END IF;
        END IF;
    END IF;
    
    IF array_length(differences, 1) > 0 THEN
        RAISE WARNING 'POST-MIGRATION WARNING: Record count differences detected:';
        FOREACH table_name IN ARRAY differences
        LOOP
            RAISE WARNING '  %', table_name;
        END LOOP;
    ELSE
        RAISE NOTICE 'PASS: Record counts match baseline';
    END IF;
END $$;

-- ============================================================================
-- 2. DATA INTEGRITY CHECKS (Re-run pre-migration checks)
-- ============================================================================

-- Check for orphaned facility records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility f
    LEFT JOIN company c ON f.company_id = c.company_id
    WHERE f.company_id IS NOT NULL AND c.company_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found % orphaned facility records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility records';
END $$;

-- Check for orphaned facility_type references
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM facility f
    LEFT JOIN facility_type ft ON f.facility_type_id = ft.facility_type_id
    WHERE f.facility_type_id IS NOT NULL AND ft.facility_type_id IS NULL;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found % orphaned facility_type references', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned facility_type references';
END $$;

-- Check for orphaned junction table records
DO $$
DECLARE
    orphaned_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphaned_count
    FROM (
        SELECT facility_id FROM facility_service fs
        LEFT JOIN facility f ON fs.facility_id = f.facility_id
        WHERE f.facility_id IS NULL
        UNION ALL
        SELECT facility_id FROM facility_product fp
        LEFT JOIN facility f ON fp.facility_id = f.facility_id
        WHERE f.facility_id IS NULL
        UNION ALL
        SELECT facility_id FROM facility_transport_mode ftm
        LEFT JOIN facility f ON ftm.facility_id = f.facility_id
        WHERE f.facility_id IS NULL
    ) orphans;
    
    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found % orphaned junction table records', orphaned_count;
    END IF;
    
    RAISE NOTICE 'PASS: No orphaned junction table records';
END $$;

-- ============================================================================
-- 3. CONSTRAINT VALIDATION
-- ============================================================================

-- Verify foreign key constraints are intact
DO $$
DECLARE
    constraint_count INTEGER;
    expected_constraints TEXT[] := ARRAY[
        'facility_company_id_fkey',
        'facility_facility_type_id_fkey',
        'facility_contact_facility_id_fkey'
    ];
    constraint_name TEXT;
    missing_constraints TEXT[] := ARRAY[]::TEXT[];
BEGIN
    FOREACH constraint_name IN ARRAY expected_constraints
    LOOP
        SELECT COUNT(*) INTO constraint_count
        FROM information_schema.table_constraints
        WHERE constraint_name = constraint_name
        AND table_schema = 'public';
        
        IF constraint_count = 0 THEN
            missing_constraints := array_append(missing_constraints, constraint_name);
        END IF;
    END LOOP;
    
    IF array_length(missing_constraints, 1) > 0 THEN
        RAISE WARNING 'POST-MIGRATION WARNING: Missing foreign key constraints: %', array_to_string(missing_constraints, ', ');
    ELSE
        RAISE NOTICE 'PASS: Foreign key constraints are intact';
    END IF;
END $$;

-- Verify unique constraints are maintained
DO $$
DECLARE
    duplicate_companies INTEGER;
    duplicate_parcels INTEGER;
BEGIN
    -- Check company names
    SELECT COUNT(*) INTO duplicate_companies
    FROM (
        SELECT name, COUNT(*) as cnt
        FROM company
        GROUP BY name
        HAVING COUNT(*) > 1
    ) duplicates;
    
    IF duplicate_companies > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found duplicate company names';
    END IF;
    
    -- Check parcel numbers if parcels table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'parcels') THEN
        SELECT COUNT(*) INTO duplicate_parcels
        FROM (
            SELECT parcelnumb, COUNT(*) as cnt
            FROM parcels
            WHERE parcelnumb IS NOT NULL
            GROUP BY parcelnumb
            HAVING COUNT(*) > 1
        ) duplicates;
        
        IF duplicate_parcels > 0 THEN
            RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found duplicate parcel numbers';
        END IF;
    END IF;
    
    RAISE NOTICE 'PASS: Unique constraints are maintained';
END $$;

-- ============================================================================
-- 4. GEOMETRY VALIDATION
-- ============================================================================

-- Verify facility geometries are still valid
DO $$
DECLARE
    invalid_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO invalid_count
    FROM facility
    WHERE geom IS NOT NULL AND NOT ST_IsValid(geom);
    
    IF invalid_count > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Found % facilities with invalid geometry', invalid_count;
    END IF;
    
    RAISE NOTICE 'PASS: All facility geometries are valid';
END $$;

-- Verify parcel geometries if parcels table exists
DO $$
DECLARE
    table_exists BOOLEAN;
    invalid_count INTEGER;
BEGIN
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'parcels'
    ) INTO table_exists;
    
    IF table_exists THEN
        SELECT COUNT(*) INTO invalid_count
        FROM parcels
        WHERE geom IS NOT NULL AND NOT ST_IsValid(geom);
        
        IF invalid_count > 0 THEN
            RAISE WARNING 'POST-MIGRATION WARNING: Found % parcels with invalid geometry', invalid_count;
        ELSE
            RAISE NOTICE 'PASS: All parcel geometries are valid';
        END IF;
    END IF;
END $$;

-- ============================================================================
-- 5. VIEW VALIDATION
-- ============================================================================

-- Verify all views can be queried
DO $$
DECLARE
    broken_views TEXT[];
    view_name TEXT;
    view_list TEXT[] := ARRAY['facility_with_names'];
BEGIN
    -- Add parcel views if they exist
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'facility_parcels_8mi') THEN
        view_list := array_append(view_list, 'facility_parcels_8mi');
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'crop_summary_by_region_year') THEN
        view_list := array_append(view_list, 'crop_summary_by_region_year');
    END IF;
    
    broken_views := ARRAY[]::TEXT[];
    
    FOREACH view_name IN ARRAY view_list
    LOOP
        BEGIN
            EXECUTE format('SELECT * FROM %I LIMIT 1', view_name);
        EXCEPTION WHEN OTHERS THEN
            broken_views := array_append(broken_views, view_name);
            RAISE WARNING 'View % is broken: %', view_name, SQLERRM;
        END;
    END LOOP;
    
    IF array_length(broken_views, 1) > 0 THEN
        RAISE EXCEPTION 'POST-MIGRATION CHECK FAILED: Broken views: %', array_to_string(broken_views, ', ');
    END IF;
    
    RAISE NOTICE 'PASS: All views are queryable';
END $$;

-- ============================================================================
-- 6. INDEX VALIDATION
-- ============================================================================

-- Verify critical indexes still exist and are valid
DO $$
DECLARE
    missing_indexes TEXT[];
    index_name TEXT;
    index_list TEXT[] := ARRAY['facility_geom_gix'];
BEGIN
    -- Add parcel indexes if parcels table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'parcels') THEN
        index_list := array_append(index_list, 'parcels_geom_gix');
        index_list := array_append(index_list, 'parcels_parcelnumb_uidx');
    END IF;
    
    missing_indexes := ARRAY[]::TEXT[];
    
    FOREACH index_name IN ARRAY index_list
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND indexname = index_name
        ) THEN
            missing_indexes := array_append(missing_indexes, index_name);
        END IF;
    END LOOP;
    
    IF array_length(missing_indexes, 1) > 0 THEN
        RAISE WARNING 'POST-MIGRATION WARNING: Missing indexes: %', array_to_string(missing_indexes, ', ');
    ELSE
        RAISE NOTICE 'PASS: Critical indexes exist';
    END IF;
END $$;

-- ============================================================================
-- 7. DATA CONSISTENCY CHECKS
-- ============================================================================

-- Verify facility lat/lon match geom (if both exist)
DO $$
DECLARE
    mismatch_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO mismatch_count
    FROM facility
    WHERE geom IS NOT NULL
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND ABS(ST_Y(geom) - latitude) > 0.0001
      AND ABS(ST_X(geom) - longitude) > 0.0001;
    
    IF mismatch_count > 0 THEN
        RAISE WARNING 'POST-MIGRATION WARNING: Found % facilities where lat/lon does not match geom', mismatch_count;
    ELSE
        RAISE NOTICE 'PASS: Facility coordinates are consistent';
    END IF;
END $$;

-- ============================================================================
-- SUMMARY
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'POST-MIGRATION CHECKS COMPLETED';
    RAISE NOTICE 'Review any warnings above';
    RAISE NOTICE 'If all checks passed, migration was successful';
    RAISE NOTICE '========================================';
END $$;

