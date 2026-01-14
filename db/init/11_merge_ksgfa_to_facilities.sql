-- Merge KGFA detail data into facilities and linked tables
-- This script:
-- 1. Creates/updates companies from KGFA data
-- 2. Creates facilities for each KGFA location
-- 3. Adds facility contacts if contact information exists
-- 4. Uses ON CONFLICT to avoid duplicates

-- Default facility type for KGFA members (Grain Elevator)
-- Default location (center of Kansas) for facilities without geocoded addresses
-- These can be updated later with actual coordinates

DO $$
DECLARE
    default_facility_type_id INT := 1; -- Grain Elevator
    default_lat DECIMAL(9,6) := 38.5000; -- Center of Kansas
    default_lon DECIMAL(9,6) := -98.0000; -- Center of Kansas
    kgfa_record RECORD;
    company_id_var INT;
    facility_id_var INT;
    contact_count INT;
BEGIN
    RAISE NOTICE 'Starting KGFA to facilities merge...';
    
    -- Loop through each KGFA record
    FOR kgfa_record IN 
        SELECT 
            ksgfa_detail_id,
            company,
            contact,
            phone,
            website,
            street,
            city,
            state,
            zip,
            notes,
            detail_url
        FROM ksgfa_detail
        ORDER BY company, city
    LOOP
        -- Step 1: Create or get company
        INSERT INTO company (name, website_url, phone_main, notes)
        VALUES (
            kgfa_record.company,
            NULLIF(kgfa_record.website, ''),
            NULLIF(kgfa_record.phone, ''),
            'Imported from KGFA directory'
        )
        ON CONFLICT (name) 
        DO UPDATE SET
            -- Update company info if we have new data and existing is null/empty
            website_url = COALESCE(NULLIF(EXCLUDED.website_url, ''), company.website_url),
            phone_main = COALESCE(NULLIF(EXCLUDED.phone_main, ''), company.phone_main),
            notes = COALESCE(
                CASE WHEN company.notes LIKE '%KGFA%' THEN company.notes 
                     ELSE company.notes || '; Imported from KGFA directory' 
                END,
                EXCLUDED.notes
            );
        
        -- Get the company_id
        SELECT c.company_id INTO company_id_var
        FROM company c
        WHERE c.name = kgfa_record.company;
        
        -- Step 2: Create facility
        -- Use company name + city as facility name if no specific facility name
        -- Or use city name as facility name
        INSERT INTO facility (
            company_id,
            facility_type_id,
            name,
            description,
            address_line1,
            city,
            state,
            postal_code,
            latitude,
            longitude,
            status,
            website_url,
            phone_main,
            notes
        )
        VALUES (
            company_id_var,
            default_facility_type_id,
            COALESCE(NULLIF(kgfa_record.city, ''), kgfa_record.company), -- Facility name defaults to city
            'KGFA member location',
            NULLIF(kgfa_record.street, ''),
            NULLIF(kgfa_record.city, ''),
            COALESCE(NULLIF(kgfa_record.state, ''), 'KS'),
            NULLIF(kgfa_record.zip, ''),
            default_lat, -- Will need geocoding later
            default_lon, -- Will need geocoding later
            'ACTIVE',
            NULLIF(kgfa_record.website, ''),
            NULLIF(kgfa_record.phone, ''),
            'Imported from KGFA: ' || kgfa_record.detail_url
        )
        ON CONFLICT (company_id, name, city, state)
        DO UPDATE SET
            -- Update facility info if changed
            address_line1 = COALESCE(NULLIF(EXCLUDED.address_line1, ''), facility.address_line1),
            postal_code = COALESCE(NULLIF(EXCLUDED.postal_code, ''), facility.postal_code),
            website_url = COALESCE(NULLIF(EXCLUDED.website_url, ''), facility.website_url),
            phone_main = COALESCE(NULLIF(EXCLUDED.phone_main, ''), facility.phone_main),
            notes = COALESCE(
                CASE WHEN facility.notes LIKE '%KGFA%' THEN facility.notes 
                     ELSE facility.notes || '; ' || EXCLUDED.notes 
                END,
                EXCLUDED.notes
            );
        
        -- Get the facility_id
        SELECT f.facility_id INTO facility_id_var
        FROM facility f
        WHERE f.company_id = company_id_var
          AND f.name = COALESCE(NULLIF(kgfa_record.city, ''), kgfa_record.company)
          AND f.city = NULLIF(kgfa_record.city, '')
          AND f.state = COALESCE(NULLIF(kgfa_record.state, ''), 'KS');
        
        -- Step 3: Create facility contact if contact name exists
        IF kgfa_record.contact IS NOT NULL AND TRIM(kgfa_record.contact) != '' THEN
            -- Check if contact already exists
            SELECT COUNT(*) INTO contact_count
            FROM facility_contact fc
            WHERE fc.facility_id = facility_id_var
              AND fc.name = kgfa_record.contact;
            
            -- Only insert if contact doesn't exist
            IF contact_count = 0 THEN
                INSERT INTO facility_contact (
                    facility_id,
                    name,
                    phone,
                    is_primary,
                    notes
                )
                VALUES (
                    facility_id_var,
                    kgfa_record.contact,
                    NULLIF(kgfa_record.phone, ''),
                    TRUE, -- Make it primary if it's the only contact
                    'Imported from KGFA'
                );
            END IF;
        END IF;
        
    END LOOP;
    
    RAISE NOTICE 'KGFA merge completed successfully!';
END $$;

-- Summary statistics
DO $$
DECLARE
    kgfa_count INT;
    company_count INT;
    facility_count INT;
    contact_count INT;
BEGIN
    SELECT COUNT(*) INTO kgfa_count FROM ksgfa_detail;
    SELECT COUNT(DISTINCT company) INTO company_count FROM ksgfa_detail;
    
    -- Count facilities created/updated from KGFA
    SELECT COUNT(*) INTO facility_count 
    FROM facility 
    WHERE notes LIKE '%KGFA%';
    
    -- Count contacts created from KGFA
    SELECT COUNT(*) INTO contact_count 
    FROM facility_contact 
    WHERE notes LIKE '%KGFA%';
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Merge Summary:';
    RAISE NOTICE '  KGFA records processed: %', kgfa_count;
    RAISE NOTICE '  Companies created/updated: %', company_count;
    RAISE NOTICE '  Facilities created/updated: %', facility_count;
    RAISE NOTICE '  Contacts created: %', contact_count;
    RAISE NOTICE '========================================';
END $$;

-- Add comments
COMMENT ON TABLE ksgfa_detail IS 'KGFA member directory source data - merged into facility/company tables via 11_merge_ksgfa_to_facilities.sql';
