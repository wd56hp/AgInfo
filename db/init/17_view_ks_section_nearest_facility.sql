-- User-facing name: nearest drive facility per KS PLSS section (after haul_ks_section_facility_routes_nearest is loaded).
CREATE OR REPLACE VIEW v_ks_section_nearest_facility AS
SELECT
    section_feature_id AS feature_id,
    section_object_id,
    section_range_township,
    plss_key,
    plss_nad83_id,
    township_number,
    range_number,
    section_number,
    facility_id AS nearest_facility_id,
    COALESCE(facility_name_canonical, route_facility_name) AS nearest_facility_name,
    company_name,
    facility_type_name,
    facility_city,
    facility_county,
    facility_state,
    crow_miles,
    drive_miles,
    drive_minutes_one_way,
    unload_minutes,
    one_way_drive_plus_unload_minutes,
    total_minutes_two_way_plus_unload,
    route_status,
    field_centroid_lon,
    field_centroid_lat,
    section_centroid_geom,
    facility_geom
FROM v_ks_section_facility_fastest_route;

COMMENT ON VIEW v_ks_section_nearest_facility IS
    'One row per section with OSM drive metrics to the best facility (see v_ks_section_facility_fastest_route).';

GRANT SELECT ON v_ks_section_nearest_facility TO agadmin;
