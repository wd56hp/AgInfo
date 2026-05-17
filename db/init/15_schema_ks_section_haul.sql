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
-- Shell tables allow CREATE TABLE on fresh databases before the first routing run.
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

DROP VIEW IF EXISTS v_ks_section_nearest_facility CASCADE;
DROP VIEW IF EXISTS v_ks_section_facility_haul_ranked CASCADE;
DROP VIEW IF EXISTS v_ks_section_facility_fastest_route CASCADE;
DROP VIEW IF EXISTS v_ks_section_facility_haul_all CASCADE;
