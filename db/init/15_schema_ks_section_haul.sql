-- Kansas PLSS sections joined to OSM drive routing (haul_routing) / facility.
--
-- Drive miles and minutes are produced by scripts/build_haul_matrix.py using the same pipeline
-- as parcels, but with section centroid points and field_id = ks_plss_section.feature_id.
-- Use dedicated PostGIS table names so parcel haul tables are untouched, for example:
--   --postgis-all-table haul_ks_section_facility_routes_all
--   --postgis-nearest-table haul_ks_section_facility_routes_nearest
--   --field-id-column feature_id
--   --owner-column 0
--
-- If GeoPandas replaces these tables (DROP CASCADE), re-apply this file so views are recreated.
--
-- Shell tables allow CREATE VIEW on fresh databases before the first routing run.
-- Column list matches haul_routing.pipeline._ROUTES_ALL_COLUMNS + PostGIS geom (+ optional lat/lon).

CREATE TABLE IF NOT EXISTS haul_ks_section_facility_routes_all (
    field_id                              BIGINT,
    owner_name                            TEXT,
    field_centroid_lon                    DOUBLE PRECISION,
    field_centroid_lat                    DOUBLE PRECISION,
    unload_minutes                        DOUBLE PRECISION,
    facility_id                           INTEGER,
    facility_name                         TEXT,
    crow_miles                            DOUBLE PRECISION,
    drive_miles                           DOUBLE PRECISION,
    drive_minutes_one_way                 DOUBLE PRECISION,
    one_way_drive_plus_unload_minutes     DOUBLE PRECISION,
    total_minutes_two_way_plus_unload     DOUBLE PRECISION,
    is_closest_facility                   BOOLEAN,
    status                                TEXT,
    geom                                  geometry(Point, 4326)
);

CREATE TABLE IF NOT EXISTS haul_ks_section_facility_routes_nearest (
    field_id                              BIGINT,
    owner_name                            TEXT,
    field_centroid_lon                    DOUBLE PRECISION,
    field_centroid_lat                    DOUBLE PRECISION,
    unload_minutes                        DOUBLE PRECISION,
    facility_id                           INTEGER,
    facility_name                         TEXT,
    crow_miles                            DOUBLE PRECISION,
    drive_miles                           DOUBLE PRECISION,
    drive_minutes_one_way                 DOUBLE PRECISION,
    one_way_drive_plus_unload_minutes     DOUBLE PRECISION,
    total_minutes_two_way_plus_unload     DOUBLE PRECISION,
    is_closest_facility                   BOOLEAN,
    status                                TEXT,
    geom                                  geometry(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_haul_ks_sec_all_field ON haul_ks_section_facility_routes_all (field_id);
CREATE INDEX IF NOT EXISTS idx_haul_ks_sec_all_fac ON haul_ks_section_facility_routes_all (facility_id);
CREATE INDEX IF NOT EXISTS idx_haul_ks_sec_nn_field ON haul_ks_section_facility_routes_nearest (field_id);

-- Every routed section × facility pair with KS PLSS attributes from ks_plss_section.
CREATE OR REPLACE VIEW v_ks_section_facility_haul_all AS
SELECT
    r.field_id AS section_feature_id,
    s.object_id AS section_object_id,
    s.section_range_township,
    k.plss_key,
    s.plss_nad83_id,
    s.township_number,
    s.range_number,
    s.section_number,
    r.owner_name AS route_owner_label,
    r.facility_id,
    r.facility_name AS route_facility_name,
    fw.name AS facility_name_canonical,
    fw.company_name,
    fw.facility_type_name,
    fw.city AS facility_city,
    fw.county AS facility_county,
    fw.state AS facility_state,
    fw.geom AS facility_geom,
    r.crow_miles,
    r.drive_miles,
    r.drive_minutes_one_way,
    r.unload_minutes,
    r.one_way_drive_plus_unload_minutes,
    r.total_minutes_two_way_plus_unload,
    r.is_closest_facility,
    r.status AS route_status,
    r.field_centroid_lon,
    r.field_centroid_lat,
    r.geom AS section_centroid_geom
FROM haul_ks_section_facility_routes_all r
LEFT JOIN ks_plss_section s ON s.feature_id = r.field_id
LEFT JOIN v_ks_plss_section_key k ON k.feature_id = r.field_id
LEFT JOIN facility_with_names fw ON fw.facility_id = r.facility_id;

-- One row per section: fastest successful drive route among prefiltered facilities (haul "nearest" table).
CREATE OR REPLACE VIEW v_ks_section_facility_fastest_route AS
SELECT
    r.field_id AS section_feature_id,
    s.object_id AS section_object_id,
    s.section_range_township,
    k.plss_key,
    s.plss_nad83_id,
    s.township_number,
    s.range_number,
    s.section_number,
    r.owner_name AS route_owner_label,
    r.facility_id,
    r.facility_name AS route_facility_name,
    fw.name AS facility_name_canonical,
    fw.company_name,
    fw.facility_type_name,
    fw.city AS facility_city,
    fw.county AS facility_county,
    fw.state AS facility_state,
    fw.geom AS facility_geom,
    r.crow_miles,
    r.drive_miles,
    r.drive_minutes_one_way,
    r.unload_minutes,
    r.one_way_drive_plus_unload_minutes,
    r.total_minutes_two_way_plus_unload,
    r.is_closest_facility,
    r.status AS route_status,
    r.field_centroid_lon,
    r.field_centroid_lat,
    r.geom AS section_centroid_geom
FROM haul_ks_section_facility_routes_nearest r
LEFT JOIN ks_plss_section s ON s.feature_id = r.field_id
LEFT JOIN v_ks_plss_section_key k ON k.feature_id = r.field_id
LEFT JOIN facility_with_names fw ON fw.facility_id = r.facility_id;

-- Successful routes only, ranked by drive time (ties broken by crow miles) within each section.
CREATE OR REPLACE VIEW v_ks_section_facility_haul_ranked AS
SELECT
    v.*,
    row_number() OVER (
        PARTITION BY v.section_feature_id
        ORDER BY v.drive_minutes_one_way ASC NULLS LAST, v.crow_miles ASC NULLS LAST
    ) AS drive_rank_in_section
FROM v_ks_section_facility_haul_all v
WHERE v.route_status = 'ok';

COMMENT ON VIEW v_ks_section_facility_haul_all IS
    'Section × facility OSM drive routes (all candidate pairs) with ks_plss_section and facility_with_names.';
COMMENT ON VIEW v_ks_section_facility_fastest_route IS
    'One row per section from haul nearest table: best drive-time facility among routed candidates.';
COMMENT ON VIEW v_ks_section_facility_haul_ranked IS
    'Routes with status ok, ranked by drive_minutes_one_way per section.';

GRANT SELECT ON v_ks_section_facility_haul_all TO agadmin;
GRANT SELECT ON v_ks_section_facility_fastest_route TO agadmin;
GRANT SELECT ON v_ks_section_facility_haul_ranked TO agadmin;
