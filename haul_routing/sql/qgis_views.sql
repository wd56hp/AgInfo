-- QGIS-friendly views for haul routing tables (run after pipeline load).
-- Layer geometry: field centroid (EPSG:4326), column name "geom".

CREATE OR REPLACE VIEW v_haul_routes_all_qgis AS
SELECT
    row_number() OVER () AS qgs_fid,
    field_id,
    owner_name,
    facility_id,
    facility_name,
    crow_miles,
    drive_miles,
    drive_minutes_one_way,
    unload_minutes,
    one_way_drive_plus_unload_minutes,
    total_minutes_two_way_plus_unload,
    is_closest_facility,
    status,
    geom
FROM haul_field_facility_routes_all;

CREATE OR REPLACE VIEW v_haul_routes_nearest_qgis AS
SELECT
    row_number() OVER () AS qgs_fid,
    field_id,
    owner_name,
    facility_id,
    facility_name,
    crow_miles,
    drive_miles,
    drive_minutes_one_way,
    unload_minutes,
    one_way_drive_plus_unload_minutes,
    total_minutes_two_way_plus_unload,
    is_closest_facility,
    status,
    geom
FROM haul_field_facility_routes_nearest;

GRANT SELECT ON v_haul_routes_all_qgis TO agadmin;
GRANT SELECT ON v_haul_routes_nearest_qgis TO agadmin;
