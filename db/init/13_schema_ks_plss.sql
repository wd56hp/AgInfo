-- Kansas PLSS reference tables (from CSV exports; attributes + areas/lengths — no geometry in source files).
-- Load with: python scripts/load_ks_plss_csv.py

-- Township / Range polygons (aggregated units, e.g. T10S-R10E)
CREATE TABLE IF NOT EXISTS ks_plss_township_range (
    objectid         INTEGER,
    t_r              TEXT NOT NULL,
    shape__area      DOUBLE PRECISION,
    shape__length    DOUBLE PRECISION,
    loaded_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ks_plss_tr_t_r ON ks_plss_township_range (t_r);

-- Section-level PLSS (Kansas DASC-style attributes)
CREATE TABLE IF NOT EXISTS ks_plss_section (
    feature_id               INTEGER,
    object_id                INTEGER,
    dasc_plss_indicator      DOUBLE PRECISION,
    perimeter_length         DOUBLE PRECISION,
    plss_nad83_id            INTEGER,
    plss_alternate_id        INTEGER,
    meridian_flag            INTEGER,
    meridian_number          INTEGER,
    township_flag            INTEGER,
    township_number          INTEGER,
    range_flag               INTEGER,
    range_number             INTEGER,
    section_flag             INTEGER,
    section_number           INTEGER,
    excluded_area_indicator_a INTEGER,
    excluded_area_indicator_b INTEGER,
    section_range_township   TEXT,
    shape_area_no_data       DOUBLE PRECISION,
    shape_length             DOUBLE PRECISION,
    computed_shape_area      DOUBLE PRECISION,
    computed_shape_length    DOUBLE PRECISION,
    loaded_at                TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ks_plss_section_str ON ks_plss_section (section_range_township);
CREATE INDEX IF NOT EXISTS idx_ks_plss_section_ids ON ks_plss_section (plss_nad83_id);

-- Quarter-quarter (1/16 section) records; TRS_Q2 encodes township, range, section, QQ code
CREATE TABLE IF NOT EXISTS ks_plss_quarter_quarter (
    fid                   BIGINT,
    objectid              INTEGER,
    recnmbr               BIGINT,
    trs_q2                TEXT NOT NULL,
    shape_area            DOUBLE PRECISION,
    shape_len             DOUBLE PRECISION,
    shape_area_computed   DOUBLE PRECISION,
    shape_len_computed    DOUBLE PRECISION,
    loaded_at             TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ks_plss_qq_trs ON ks_plss_quarter_quarter (trs_q2);
CREATE INDEX IF NOT EXISTS idx_ks_plss_qq_recnmbr ON ks_plss_quarter_quarter (recnmbr);

-- ---------- Views: parsed township / range (from t_r like T10S-R10E)

CREATE OR REPLACE VIEW v_ks_plss_township_range_parsed AS
SELECT
    tr.objectid,
    tr.t_r,
    tr.shape__area,
    tr.shape__length,
    tr.loaded_at,
    rm.parts[1]::integer AS township_number,
    rm.parts[2]          AS township_ns,
    rm.parts[3]::integer AS range_number,
    rm.parts[4]          AS range_ew,
    format('T%s%s R%s%s', rm.parts[1], rm.parts[2], rm.parts[3], rm.parts[4]) AS str_standard
FROM ks_plss_township_range tr
CROSS JOIN LATERAL (
    SELECT regexp_match(tr.t_r, '^T(\d+)([NS])-R(\d+)([EW])$') AS parts
) rm
WHERE rm.parts IS NOT NULL;

-- ---------- Views: parsed section string (S22-T4S-R37W)

CREATE OR REPLACE VIEW v_ks_plss_section_parsed AS
SELECT
    s.feature_id,
    s.object_id,
    s.dasc_plss_indicator,
    s.perimeter_length,
    s.plss_nad83_id,
    s.plss_alternate_id,
    s.meridian_flag,
    s.meridian_number,
    s.township_flag,
    s.township_number,
    s.range_flag,
    s.range_number,
    s.section_flag,
    s.section_number,
    s.excluded_area_indicator_a,
    s.excluded_area_indicator_b,
    s.section_range_township,
    s.shape_area_no_data,
    s.shape_length,
    s.computed_shape_area,
    s.computed_shape_length,
    s.loaded_at,
    rm.parts[1]::integer AS section_number_parsed,
    rm.parts[2]::integer AS township_number_parsed,
    rm.parts[3]          AS township_ns_parsed,
    rm.parts[4]::integer AS range_number_parsed,
    rm.parts[5]          AS range_ew_parsed
FROM ks_plss_section s
CROSS JOIN LATERAL (
    SELECT regexp_match(
        s.section_range_township,
        '^S(\d+)-T(\d+)([NS])-R(\d+)([EW])$'
    ) AS parts
) rm
WHERE s.section_range_township IS NOT NULL AND rm.parts IS NOT NULL;

CREATE OR REPLACE VIEW v_ks_plss_section_key AS
SELECT
    p.*,
    format(
        'S%s T%s%s R%s%s',
        p.section_number_parsed,
        p.township_number_parsed,
        p.township_ns_parsed,
        p.range_number_parsed,
        p.range_ew_parsed
    ) AS plss_key
FROM v_ks_plss_section_parsed p;

-- ---------- Views: parsed TRS_Q2 (e.g. 05S19E02SENW = T5S R19E Sec 2, sixteenth SENW)

CREATE OR REPLACE VIEW v_ks_plss_qq_parsed AS
SELECT
    q.fid,
    q.objectid,
    q.recnmbr,
    q.trs_q2,
    q.shape_area,
    q.shape_len,
    q.shape_area_computed,
    q.shape_len_computed,
    q.loaded_at,
    rm.parts[1]::integer AS township_number,
    rm.parts[2]          AS township_ns,
    rm.parts[3]::integer AS range_number,
    rm.parts[4]          AS range_ew,
    rm.parts[5]::integer AS section_number,
    rm.parts[6]          AS qq_code,
    substring(rm.parts[6] FROM 1 FOR 2) AS quarter_section,
    substring(rm.parts[6] FROM 3 FOR 2) AS sixteenth_within_quarter,
    format('S%s T%s%s R%s%s', rm.parts[5]::integer, rm.parts[1], rm.parts[2], rm.parts[3], rm.parts[4])
        AS plss_key,
    format('T%s%s R%s%s', rm.parts[1], rm.parts[2], rm.parts[3], rm.parts[4]) AS township_range_key
FROM ks_plss_quarter_quarter q
CROSS JOIN LATERAL (
    SELECT regexp_match(
        q.trs_q2, '^(\d{1,2})([NS])(\d{1,2})([EW])(\d{1,2})([NSEW]{4})$'
    ) AS parts
) rm
WHERE rm.parts IS NOT NULL;

COMMENT ON TABLE ks_plss_township_range IS 'Kansas PLSS township/range units from CSV (e.g. T10S-R10E).';
COMMENT ON TABLE ks_plss_section IS 'Kansas PLSS section polygons/attributes (S22-T4S-R37W style).';
COMMENT ON TABLE ks_plss_quarter_quarter IS 'Kansas PLSS 1/16 section (quarter-quarter) with TRS_Q2 key.';
COMMENT ON VIEW v_ks_plss_qq_parsed IS 'QQ rows with township, range, section, quarter codes parsed from TRS_Q2.';
