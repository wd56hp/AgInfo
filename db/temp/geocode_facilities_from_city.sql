-- Attempt to geocode facilities using city/state lookup
-- This uses a simple approach: looks up coordinates from parcels table if available
-- or uses known city coordinates. This is a basic approach - for production,
-- use a proper geocoding service like Google Maps API, OpenStreetMap Nominatim, etc.

-- Note: This is a placeholder - you'll need to either:
-- 1. Use an external geocoding API to update lat/lon
-- 2. Match against a cities/counties reference table with coordinates
-- 3. Use parcels data if cities match

-- For now, this shows facilities that need geocoding
SELECT 
    f.facility_id,
    f.name,
    f.address_line1,
    f.city,
    f.state,
    f.postal_code,
    f.latitude,
    f.longitude,
    CASE 
        WHEN f.latitude = 38.5000 AND f.longitude = -98.0000 THEN 'NEEDS_GEOCODING'
        ELSE 'HAS_COORDS'
    END as geocoding_status
FROM facility f
WHERE f.notes LIKE '%KGFA%'
  AND f.latitude = 38.5000 
  AND f.longitude = -98.0000
ORDER BY f.state, f.city
LIMIT 20;

-- Count of facilities needing geocoding
SELECT 
    COUNT(*) as facilities_needing_geocoding,
    COUNT(DISTINCT city || ', ' || state) as unique_cities
FROM facility
WHERE notes LIKE '%KGFA%'
  AND latitude = 38.5000 
  AND longitude = -98.0000;
