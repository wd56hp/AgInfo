-- Update geometry (geom) for facilities from latitude/longitude
-- This ensures all facilities have proper PostGIS geometry even if trigger didn't fire
-- Note: This updates geom from existing lat/lon. To get actual coordinates, 
-- addresses need to be geocoded first to update latitude/longitude values.

DO $$
DECLARE
    updated_count INT := 0;
    facility_record RECORD;
BEGIN
    RAISE NOTICE 'Starting geometry update for facilities...';
    
    -- Update geom for all facilities that have lat/lon but missing or incorrect geom
    FOR facility_record IN
        SELECT 
            facility_id,
            name,
            city,
            latitude,
            longitude,
            geom
        FROM facility
        WHERE latitude IS NOT NULL 
          AND longitude IS NOT NULL
          AND (
              geom IS NULL 
              OR ST_X(geom) != longitude 
              OR ST_Y(geom) != latitude
          )
    LOOP
        -- Update the geometry from lat/lon
        UPDATE facility
        SET geom = ST_SetSRID(
            ST_MakePoint(
                facility_record.longitude::DOUBLE PRECISION,
                facility_record.latitude::DOUBLE PRECISION
            ),
            4326
        )
        WHERE facility_id = facility_record.facility_id;
        
        updated_count := updated_count + 1;
    END LOOP;
    
    RAISE NOTICE 'Updated geometry for % facilities', updated_count;
END $$;

-- Verify results
SELECT 
    COUNT(*) as total_facilities,
    COUNT(geom) as facilities_with_geom,
    COUNT(*) FILTER (WHERE geom IS NULL) as facilities_without_geom,
    COUNT(*) FILTER (WHERE latitude = 38.5000 AND longitude = -98.0000) as facilities_with_default_coords
FROM facility;
