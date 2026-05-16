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

-- Live nearest row per section site (optional; same logic as compute insert — can be slow for full state in QGIS)
CREATE OR REPLACE VIEW v_ks_section_nearest_grain_elevator AS
SELECT
    s.feature_id,
    COALESCE(k.plss_key, sec.section_range_township) AS plss_key,
    COALESCE(k.section_range_township, sec.section_range_township) AS section_range_township,
    s.geom AS section_geom,
    nf.facility_id AS nearest_facility_id,
    nf.name AS nearest_facility_name,
    nf.company_id,
    nf.geom AS facility_geom,
    ST_Distance(s.geom::geography, nf.geom::geography) / 1609.344::double precision AS distance_miles,
    ST_MakeLine(s.geom, nf.geom) AS connector_line,
    nf.facility_type_id,
    now() AS view_generated_at
FROM ks_plss_section_site s
LEFT JOIN v_ks_plss_section_key k ON k.feature_id = s.feature_id
LEFT JOIN ks_plss_section sec ON sec.feature_id = s.feature_id
CROSS JOIN LATERAL (
    SELECT f.facility_id, f.name, f.company_id, f.geom, f.facility_type_id
    FROM facility f
    WHERE f.facility_type_id = 1
      AND f.geom IS NOT NULL
      AND COALESCE(f.status, 'ACTIVE') = 'ACTIVE'
    ORDER BY s.geom <-> f.geom
    LIMIT 1
) nf;

COMMENT ON VIEW v_ks_section_nearest_grain_elevator IS
    'Nearest grain elevator (facility_type_id = 1) per ks_plss_section_site using KNN + geography distance in miles.';
