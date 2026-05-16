-- Representative section centroids from parcel geometry (county / field coverage only).
-- For statewide section points use scripts/load_ks_section_sites_from_dasc.py (DASC ArcGIS).
-- Builds the same key as parcel columns plss_section + plss_township + plss_range (Kansas).
-- Only sections that appear in ks_plss_section and have at least one matching parcel get a site.

DELETE FROM ks_plss_section_site WHERE source_note = 'parcel_plss_aggregate';

INSERT INTO ks_plss_section_site (feature_id, geom, source_note, plss_key, section_range_township)
SELECT
    s.feature_id,
    (ST_PointOnSurface(ST_Centroid(p.gc)))::geometry(Point, 4326),
    'parcel_plss_aggregate',
    k.plss_key,
    btrim(s.section_range_township)
FROM (
    SELECT
        upper(
            btrim(
                'S' || btrim(regexp_replace(plss_section, '[^0-9]', '', 'g'))
                || '-'
                || regexp_replace(btrim(plss_township), '^0*([0-9]+)([NS])$', 'T\1\2')
                || '-'
                || regexp_replace(btrim(plss_range), '^0*([0-9]+)([EW])$', 'R\1\2')
            )
        ) AS dasc_u,
        ST_Collect(geom::geometry) AS gc
    FROM parcels
    WHERE geom IS NOT NULL
      AND plss_section IS NOT NULL AND btrim(plss_section) <> ''
      AND plss_township IS NOT NULL AND btrim(plss_township) <> ''
      AND plss_range IS NOT NULL AND btrim(plss_range) <> ''
    GROUP BY 1
) p
JOIN ks_plss_section s ON upper(btrim(s.section_range_township)) = p.dasc_u
LEFT JOIN v_ks_plss_section_key k ON k.feature_id = s.feature_id;

COMMENT ON TABLE ks_plss_section_site IS
    'Section routing origins; parcel_plss_aggregate rows derived from ST_Collect(parcel.geom) by DASC key.';
