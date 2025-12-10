-- Core schema for AgInfo
-- Requires PostGIS extension (enabled in 01_enable_postgis.sql)

-- 1. company ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS company (
    company_id      SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL UNIQUE,
    website_url     VARCHAR(300),
    phone_main      VARCHAR(50),
    notes           TEXT
);

-- 2. facility_type ----------------------------------------------------

CREATE TABLE IF NOT EXISTS facility_type (
    facility_type_id    SERIAL PRIMARY KEY,
    name                VARCHAR(100) NOT NULL UNIQUE,  -- e.g. 'Grain Elevator', 'Ethanol Plant'
    description         TEXT,
    is_producer         BOOLEAN DEFAULT FALSE, -- produces product
    is_consumer         BOOLEAN DEFAULT FALSE, -- consumes product
    is_storage          BOOLEAN DEFAULT FALSE  -- provides storage
);

-- 3. facility ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS facility (
    facility_id         SERIAL PRIMARY KEY,
    company_id          INT REFERENCES company(company_id),
    facility_type_id    INT REFERENCES facility_type(facility_type_id),

    name                VARCHAR(200) NOT NULL,
    description         TEXT,

    -- address
    address_line1       VARCHAR(200),
    address_line2       VARCHAR(200),
    city                VARCHAR(100),
    county              VARCHAR(100),
    state               CHAR(2) DEFAULT 'KS',
    postal_code         VARCHAR(20),

    -- map location
    latitude            DECIMAL(9,6) NOT NULL,
    longitude           DECIMAL(9,6) NOT NULL,

    -- handy geometry for GIS use
    geom                geometry(Point, 4326),

    status              VARCHAR(20) DEFAULT 'ACTIVE', -- ACTIVE / INACTIVE / PLANNED
    opened_year         SMALLINT,
    closed_year         SMALLINT,
    website_url         VARCHAR(300),
    phone_main          VARCHAR(50),
    email_main          VARCHAR(200),

    notes               TEXT
);

-- keep lat/long and geom in sync when inserting without geom
CREATE OR REPLACE FUNCTION facility_set_geom()
RETURNS trigger AS $$
BEGIN
  IF NEW.geom IS NULL AND NEW.longitude IS NOT NULL AND NEW.latitude IS NOT NULL THEN
    NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude::DOUBLE PRECISION,
                                        NEW.latitude::DOUBLE PRECISION), 4326);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_facility_set_geom ON facility;

CREATE TRIGGER trg_facility_set_geom
BEFORE INSERT OR UPDATE ON facility
FOR EACH ROW
EXECUTE FUNCTION facility_set_geom();

-- 4. facility_contact -------------------------------------------------

CREATE TABLE IF NOT EXISTS facility_contact (
    contact_id      SERIAL PRIMARY KEY,
    facility_id     INT NOT NULL REFERENCES facility(facility_id),

    name            VARCHAR(200) NOT NULL,
    role_title      VARCHAR(150), -- e.g. 'Location Manager'
    phone           VARCHAR(50),
    email           VARCHAR(200),

    is_primary      BOOLEAN DEFAULT FALSE,
    notes           TEXT
);

-- 5. service_type -----------------------------------------------------

CREATE TABLE IF NOT EXISTS service_type (
    service_type_id SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL UNIQUE,
    category        VARCHAR(50),          -- 'GRAIN', 'FERTILIZER', 'FUEL', 'FEED', 'OTHER'
    description     TEXT
);

-- 6. facility_service -------------------------------------------------

CREATE TABLE IF NOT EXISTS facility_service (
    facility_id      INT NOT NULL REFERENCES facility(facility_id),
    service_type_id  INT NOT NULL REFERENCES service_type(service_type_id),
    is_active        BOOLEAN DEFAULT TRUE,
    notes            TEXT,
    PRIMARY KEY (facility_id, service_type_id)
);

-- 7. product ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS product (
    product_id      SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL UNIQUE,  -- 'Wheat', 'NH3', 'Diesel', etc.
    category        VARCHAR(50),                   -- 'GRAIN', 'FERTILIZER', 'FUEL', 'FEED', 'CHEMICAL', 'BYPRODUCT', 'OTHER'
    unit_default    VARCHAR(20),                   -- 'BU', 'GAL', 'TON'
    description     TEXT
);

-- 8. facility_product -------------------------------------------------

CREATE TABLE IF NOT EXISTS facility_product (
    facility_id     INT NOT NULL REFERENCES facility(facility_id),
    product_id      INT NOT NULL REFERENCES product(product_id),

    -- how the product flows relative to this facility
    flow_role       VARCHAR(20) NOT NULL,   -- 'INBOUND', 'OUTBOUND', 'BOTH'
    usage_role      VARCHAR(20) NOT NULL,   -- 'CONSUMES', 'PRODUCES', 'STORES', 'RETAILS', 'HANDLES'

    is_bulk         BOOLEAN DEFAULT TRUE,
    notes           TEXT,

    PRIMARY KEY (facility_id, product_id, flow_role, usage_role)
);

-- 9. transport_mode ---------------------------------------------------

CREATE TABLE IF NOT EXISTS transport_mode (
    transport_mode_id  SERIAL PRIMARY KEY,
    name               VARCHAR(50) NOT NULL UNIQUE  -- 'TRUCK', 'RAIL', 'BARGE', 'PIPELINE'
);

-- 10. facility_transport_mode -----------------------------------------

CREATE TABLE IF NOT EXISTS facility_transport_mode (
    facility_id        INT NOT NULL REFERENCES facility(facility_id),
    transport_mode_id  INT NOT NULL REFERENCES transport_mode(transport_mode_id),
    notes              TEXT,
    PRIMARY KEY (facility_id, transport_mode_id)
);

-- Optional: basic lookup seeds ----------------------------------------

INSERT INTO transport_mode (name)
VALUES ('TRUCK'), ('RAIL'), ('BARGE'), ('PIPELINE')
ON CONFLICT (name) DO NOTHING;

INSERT INTO facility_type (name, description, is_storage, is_consumer, is_producer)
VALUES
  ('Grain Elevator', 'Country or terminal grain elevator', TRUE, FALSE, FALSE),
  ('Ethanol Plant', 'Fuel ethanol facility', FALSE, TRUE, TRUE),
  ('Feedlot', 'Cattle feedyard', FALSE, TRUE, FALSE),
  ('Fertilizer Plant', 'Fertilizer storage and blending', TRUE, TRUE, FALSE)
ON CONFLICT (name) DO NOTHING;
