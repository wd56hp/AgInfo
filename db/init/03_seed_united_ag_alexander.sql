-- Seed data: United Ag Services - Alexander, KS

-- Company -------------------------------------------------------------

INSERT INTO company (name, website_url, phone_main)
VALUES ('United Ag Services', NULL, '785-343-2255')
ON CONFLICT (name) DO NOTHING;

-- Services offered ----------------------------------------------------

INSERT INTO service_type (name, category, description) VALUES
  ('24 Hr Fuel',        'FUEL',       '24 hour cardtrol / pump fuel'),
  ('Anhydrous Ammonia', 'FERTILIZER', 'NH3 retail and application'),
  ('Chemical',          'CHEMICAL',   'Crop protection products'),
  ('Seed',              'SEED',       'Seed sales'),
  ('Bagged Feed',       'FEED',       'Bagged livestock feed'),
  ('Batteries',         'OTHER',      'Batteries'),
  ('Farm Supplies',     'OTHER',      'General farm supplies')
ON CONFLICT (name) DO NOTHING;

-- Products carried ----------------------------------------------------

INSERT INTO product (name, category, unit_default, description) VALUES
  ('Anhydrous Ammonia (NH3)', 'FERTILIZER', 'TON', 'Anhydrous ammonia'),
  ('Diesel',                  'FUEL',       'GAL', 'Diesel fuel'),
  ('Unleaded Gasoline',       'FUEL',       'GAL', 'Gasoline'),
  ('Ag Chemicals',            'CHEMICAL',   'GAL', 'Crop protection products'),
  ('Seed',                    'SEED',       'UNIT','Seed'),
  ('Bagged Feed',             'FEED',       'TON', 'Bagged livestock feed'),
  ('Batteries',               'OTHER',      NULL,  'Batteries'),
  ('Farm Supplies',           'OTHER',      NULL,  'General farm supplies')
ON CONFLICT (name) DO NOTHING;

-- Facility: Alexander location ----------------------------------------

-- Coordinates: 200 W K-96, Alexander, KS 67513
-- Lat/Lon: 38.471820, -99.551400  (WGS84)

INSERT INTO facility (
    company_id,
    facility_type_id,
    name,
    description,
    address_line1,
    city,
    county,
    state,
    postal_code,
    latitude,
    longitude,
    status,
    phone_main,
    notes
)
VALUES (
    (SELECT company_id FROM company WHERE name = 'United Ag Services'),
    (SELECT facility_type_id FROM facility_type WHERE name = 'Grain Elevator'),
    'Alexander',
    'United Ag Services - Alexander location',
    '200 W K-96',
    'Alexander',
    'Rush',
    'KS',
    '67513',
    38.471820,
    -99.551400,
    'ACTIVE',
    '785-343-2255',
    'Grain elevator with 24 hr fuel, NH3, chemical, seed, feed, and farm supplies.'
);

-- Facility geometry will be auto-populated by trigger
-- but we can force it for this row just in case:
UPDATE facility
SET geom = ST_SetSRID(ST_MakePoint(longitude::DOUBLE PRECISION,
                                   latitude::DOUBLE PRECISION), 4326)
WHERE name = 'Alexander'
  AND address_line1 = '200 W K-96';

-- Facility contact ----------------------------------------------------

INSERT INTO facility_contact (
    facility_id,
    name,
    role_title,
    phone,
    is_primary
)
VALUES (
    (SELECT facility_id FROM facility
     WHERE name = 'Alexander'
       AND address_line1 = '200 W K-96'),
    'Gene Dysinger',
    'Location Manager',
    '785-343-2255',
    TRUE
);

-- Facility services ---------------------------------------------------

INSERT INTO facility_service (facility_id, service_type_id)
SELECT
  f.facility_id,
  s.service_type_id
FROM facility f
JOIN service_type s
  ON s.name IN (
    '24 Hr Fuel',
    'Anhydrous Ammonia',
    'Chemical',
    'Seed',
    'Bagged Feed',
    'Batteries',
    'Farm Supplies'
  )
WHERE f.name = 'Alexander'
  AND f.address_line1 = '200 W K-96'
ON CONFLICT (facility_id, service_type_id) DO NOTHING;

-- Facility products (all as INBOUND / RETAILS) -----------------------

INSERT INTO facility_product (facility_id, product_id, flow_role, usage_role, is_bulk)
SELECT
  f.facility_id,
  p.product_id,
  'INBOUND'  AS flow_role,
  'RETAILS'  AS usage_role,
  TRUE       AS is_bulk
FROM facility f
JOIN product p
  ON p.name IN (
    'Anhydrous Ammonia (NH3)',
    'Diesel',
    'Unleaded Gasoline',
    'Ag Chemicals',
    'Seed',
    'Bagged Feed',
    'Batteries',
    'Farm Supplies'
  )
WHERE f.name = 'Alexander'
  AND f.address_line1 = '200 W K-96'
ON CONFLICT (facility_id, product_id, flow_role, usage_role) DO NOTHING;

-- Transport modes (assume truck only for now) ------------------------

INSERT INTO facility_transport_mode (facility_id, transport_mode_id)
SELECT
  f.facility_id,
  t.transport_mode_id
FROM facility f
JOIN transport_mode t ON t.name = 'TRUCK'
WHERE f.name = 'Alexander'
  AND f.address_line1 = '200 W K-96'
ON CONFLICT (facility_id, transport_mode_id) DO NOTHING;

