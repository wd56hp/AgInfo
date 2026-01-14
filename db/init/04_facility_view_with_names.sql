-- Create a comprehensive view that includes company and facility type names
-- This view joins all related data together for rendering on web pages
-- This is the primary view used by GeoServer to expose facility data with readable names
-- instead of just IDs, eliminating the need for separate lookups

CREATE OR REPLACE VIEW facility_with_names AS
SELECT 
    -- Facility identifiers
    f.facility_id,
    f.name,
    f.description,
    f.status,
    
    -- Company information
    f.company_id,
    c.name AS company_name,
    c.website_url AS company_website_url,
    c.phone_main AS company_phone_main,
    
    -- Facility type information
    f.facility_type_id,
    ft.name AS facility_type_name,
    ft.description AS facility_type_description,
    ft.is_producer AS facility_type_is_producer,
    ft.is_consumer AS facility_type_is_consumer,
    ft.is_storage AS facility_type_is_storage,
    
    -- Address information
    f.address_line1,
    f.address_line2,
    f.city,
    f.county,
    f.state,
    f.postal_code,
    
    -- Location/GIS information
    f.latitude,
    f.longitude,
    f.geom,
    
    -- Facility metadata
    f.opened_year,
    f.closed_year,
    f.website_url,
    f.phone_main,
    f.email_main,
    f.notes
    
FROM facility f
LEFT JOIN company c ON f.company_id = c.company_id
LEFT JOIN facility_type ft ON f.facility_type_id = ft.facility_type_id;

-- Grant permissions for GeoServer user
GRANT SELECT ON facility_with_names TO agadmin;

-- Add comment
COMMENT ON VIEW facility_with_names IS 
    'Comprehensive facility view with company and facility type information joined together. '
    'This is the primary view used by GeoServer and web applications for rendering facility data. '
    'All related lookup data (company names, facility type names) are included to eliminate '
    'the need for separate lookup queries or client-side joins.';





