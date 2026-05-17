-- Kansas PLSS section sites → nearest grain elevator (generic; separate from parcels / haul_routing).
-- Section centroids/polygons are not in ks_plss_* CSV imports; load representative points into ks_plss_section_site
-- (see scripts/build_ks_section_elevator_map.py), then populate ks_section_nearest_grain_elevator.

CREATE TABLE IF NOT EXISTS ks_plss_section_site (
    feature_id               INTEGER PRIMARY KEY,
    plss_key                 TEXT,
    section_range_township   TEXT,
    geom                       geometry(Point, 4326) NOT NULL,
    source_note                TEXT,
    loaded_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ks_plss_section_site_gist
    ON ks_plss_section_site USING gist (geom);

COMMENT ON TABLE ks_plss_section_site IS
    'Representative point per KS PLSS section (feature_id matches ks_plss_section.feature_id). Load from external section boundaries / cenroids.';

-- Speed up KNN lateral joins from sections to facilities
CREATE INDEX IF NOT EXISTS idx_facility_geom_gist
    ON facility USING gist (geom)
    WHERE geom IS NOT NULL;

CREATE TABLE IF NOT EXISTS ks_section_nearest_grain_elevator (
    feature_id                INTEGER PRIMARY KEY,
    plss_key                  TEXT,
    section_range_township    TEXT,
    section_geom              geometry(Point, 4326) NOT NULL,
    nearest_facility_id       INTEGER NOT NULL REFERENCES facility (facility_id),
    nearest_facility_name     TEXT NOT NULL,
    company_id                INTEGER REFERENCES company (company_id),
    facility_geom             geometry(Point, 4326),
    distance_miles            DOUBLE PRECISION NOT NULL,
    connector_line            geometry(LineString, 4326),
    facility_type_id          INTEGER NOT NULL,
    computed_at               TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ks_sec_near_fac ON ks_section_nearest_grain_elevator (nearest_facility_id);
CREATE INDEX IF NOT EXISTS idx_ks_sec_near_gix ON ks_section_nearest_grain_elevator USING gist (section_geom);

COMMENT ON TABLE ks_section_nearest_grain_elevator IS
    'Crow-flight (geodesic) miles from each section site point to the nearest active grain elevator in facility; built by build_ks_section_elevator_map.py compute.';

-- QGIS: same rows/columns as the table (choose geometry column in layer properties if needed).
DROP VIEW IF EXISTS v_ks_section_nearest_grain_elevator CASCADE;
CREATE OR REPLACE VIEW v_ks_section_nearest_grain_elevator AS
SELECT
    feature_id,
    plss_key,
    section_range_township,
    section_geom,
    nearest_facility_id,
    nearest_facility_name,
    company_id,
    facility_geom,
    distance_miles,
    connector_line,
    facility_type_id,
    computed_at
FROM ks_section_nearest_grain_elevator;

COMMENT ON VIEW v_ks_section_nearest_grain_elevator IS
    'Geodesic nearest grain elevator per section (reads ks_section_nearest_grain_elevator). For QGIS: section points use section_geom; facilities use facility_geom; crow links use connector_line or the line-only view below.';

-- QGIS: single LineString geometry column named geom (spider / connector layer).
DROP VIEW IF EXISTS v_ks_section_nearest_elevator_line CASCADE;
CREATE OR REPLACE VIEW v_ks_section_nearest_elevator_line AS
SELECT
    feature_id,
    plss_key,
    section_range_township,
    nearest_facility_id,
    nearest_facility_name,
    company_id,
    distance_miles,
    computed_at,
    connector_line AS geom
FROM ks_section_nearest_grain_elevator
WHERE connector_line IS NOT NULL;

COMMENT ON VIEW v_ks_section_nearest_elevator_line IS
    'Crow-flight lines section → nearest elevator (geom). Pair with v_ks_section_nearest_grain_elevator for points.';

GRANT SELECT ON v_ks_section_nearest_grain_elevator TO agadmin;
GRANT SELECT ON v_ks_section_nearest_elevator_line TO agadmin;
