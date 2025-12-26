-- Create a view that includes company and facility type names
-- This view can be used in GeoServer to expose facility data with readable names
-- instead of just IDs

CREATE OR REPLACE VIEW facility_with_names AS
SELECT 
    f.facility_id,
    f.company_id,
    c.name AS company_name,
    f.facility_type_id,
    ft.name AS facility_type_name,
    f.name,
    f.description,
    f.address_line1,
    f.address_line2,
    f.city,
    f.county,
    f.state,
    f.postal_code,
    f.latitude,
    f.longitude,
    f.geom,
    f.status,
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
COMMENT ON VIEW facility_with_names IS 'Facility view with company and facility type names joined for GeoServer use';





