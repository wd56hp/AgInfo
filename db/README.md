# AgInfo Database Schema

## Overview

The AgInfo database is a PostgreSQL database with PostGIS extension that stores information about agricultural facilities, companies, services, products, and their relationships. It is designed to support mapping and querying of agricultural infrastructure.

## Database Technology

- **Database**: PostgreSQL 16
- **Extension**: PostGIS 3.4 (for geospatial data)
- **Schema**: `aginfo`

## Schema Structure

The database consists of 15 core tables and 13 views organized into logical groups:

### Core Entity Tables

#### 1. `company`
Stores company/organization information.

| Column | Type | Description |
|--------|------|-------------|
| `company_id` | SERIAL PRIMARY KEY | Unique identifier |
| `name` | VARCHAR(200) NOT NULL UNIQUE | Company name |
| `website_url` | VARCHAR(300) | Company website |
| `phone_main` | VARCHAR(50) | Main phone number |
| `notes` | TEXT | Additional notes |

**Example**: United Ag Services, Cargill, ADM

---

#### 2. `facility_type`
Defines types of facilities (e.g., Grain Elevator, Ethanol Plant).

| Column | Type | Description |
|--------|------|-------------|
| `facility_type_id` | SERIAL PRIMARY KEY | Unique identifier |
| `name` | VARCHAR(100) NOT NULL UNIQUE | Facility type name |
| `description` | TEXT | Description of facility type |
| `is_producer` | BOOLEAN DEFAULT FALSE | Produces products |
| `is_consumer` | BOOLEAN DEFAULT FALSE | Consumes products |
| `is_storage` | BOOLEAN DEFAULT FALSE | Provides storage |

**Pre-seeded types**:
- Grain Elevator (storage)
- Ethanol Plant (producer, consumer)
- Feedlot (consumer)
- Fertilizer Plant (storage, consumer)

---

#### 3. `facility`
The main table storing facility/location information with geospatial data.

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | SERIAL PRIMARY KEY | Unique identifier |
| `company_id` | INT REFERENCES company | Parent company |
| `facility_type_id` | INT REFERENCES facility_type | Type of facility |
| `name` | VARCHAR(200) NOT NULL | Facility name |
| `description` | TEXT | Facility description |
| `address_line1` | VARCHAR(200) | Street address |
| `address_line2` | VARCHAR(200) | Additional address info |
| `city` | VARCHAR(100) | City |
| `county` | VARCHAR(100) | County |
| `state` | CHAR(2) DEFAULT 'KS' | State code |
| `postal_code` | VARCHAR(20) | ZIP/postal code |
| `latitude` | DECIMAL(9,6) NOT NULL | Latitude (WGS84) |
| `longitude` | DECIMAL(9,6) NOT NULL | Longitude (WGS84) |
| `geom` | geometry(Point, 4326) | PostGIS point geometry |
| `status` | VARCHAR(20) DEFAULT 'ACTIVE' | ACTIVE/INACTIVE/PLANNED |
| `opened_year` | SMALLINT | Year facility opened |
| `closed_year` | SMALLINT | Year facility closed |
| `website_url` | VARCHAR(300) | Facility website |
| `phone_main` | VARCHAR(50) | Main phone |
| `email_main` | VARCHAR(200) | Main email |
| `notes` | TEXT | Additional notes |

**Key Features**:
- Automatic geometry generation: A trigger (`trg_facility_set_geom`) automatically creates the `geom` point from `latitude`/`longitude` if not provided
- Spatial indexing: The `geom` column supports spatial queries using PostGIS functions

---

#### 4. `facility_contact`
Stores contact persons for facilities.

| Column | Type | Description |
|--------|------|-------------|
| `contact_id` | SERIAL PRIMARY KEY | Unique identifier |
| `facility_id` | INT REFERENCES facility | Associated facility |
| `name` | VARCHAR(200) NOT NULL | Contact name |
| `role_title` | VARCHAR(150) | Job title/role |
| `phone` | VARCHAR(50) | Contact phone |
| `email` | VARCHAR(200) | Contact email |
| `is_primary` | BOOLEAN DEFAULT FALSE | Primary contact flag |
| `notes` | TEXT | Additional notes |

---

### Service & Product Tables

#### 5. `service_type`
Defines types of services offered (e.g., 24 Hr Fuel, Anhydrous Ammonia).

| Column | Type | Description |
|--------|------|-------------|
| `service_type_id` | SERIAL PRIMARY KEY | Unique identifier |
| `name` | VARCHAR(150) NOT NULL UNIQUE | Service name |
| `category` | VARCHAR(50) | Category (FUEL, FERTILIZER, CHEMICAL, FEED, OTHER) |
| `description` | TEXT | Service description |

**Example services**:
- 24 Hr Fuel (FUEL)
- Anhydrous Ammonia (FERTILIZER)
- Chemical (CHEMICAL)
- Seed (SEED)
- Bagged Feed (FEED)

---

#### 6. `facility_service`
Junction table linking facilities to services they offer.

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | INT REFERENCES facility | Facility |
| `service_type_id` | INT REFERENCES service_type | Service type |
| `is_active` | BOOLEAN DEFAULT TRUE | Service active status |
| `notes` | TEXT | Additional notes |

**Primary Key**: `(facility_id, service_type_id)`

---

#### 7. `product`
Defines products handled (e.g., Wheat, Diesel, NH3).

| Column | Type | Description |
|--------|------|-------------|
| `product_id` | SERIAL PRIMARY KEY | Unique identifier |
| `name` | VARCHAR(150) NOT NULL UNIQUE | Product name |
| `category` | VARCHAR(50) | Category (GRAIN, FERTILIZER, FUEL, FEED, CHEMICAL, BYPRODUCT, OTHER) |
| `unit_default` | VARCHAR(20) | Default unit (BU, GAL, TON, etc.) |
| `description` | TEXT | Product description |

**Example products**:
- Anhydrous Ammonia (NH3) - FERTILIZER - TON
- Diesel - FUEL - GAL
- Seed - SEED - UNIT

---

#### 8. `facility_product`
Junction table linking facilities to products with flow and usage roles.

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | INT REFERENCES facility | Facility |
| `product_id` | INT REFERENCES product | Product |
| `flow_role` | VARCHAR(20) NOT NULL | INBOUND / OUTBOUND / BOTH |
| `usage_role` | VARCHAR(20) NOT NULL | CONSUMES / PRODUCES / STORES / RETAILS / HANDLES |
| `is_bulk` | BOOLEAN DEFAULT TRUE | Bulk handling flag |
| `notes` | TEXT | Additional notes |

**Primary Key**: `(facility_id, product_id, flow_role, usage_role)`

**Flow Roles**:
- `INBOUND`: Product comes into facility
- `OUTBOUND`: Product leaves facility
- `BOTH`: Product flows both ways

**Usage Roles**:
- `CONSUMES`: Facility consumes the product
- `PRODUCES`: Facility produces the product
- `STORES`: Facility stores the product
- `RETAILS`: Facility sells the product
- `HANDLES`: Facility handles/transfers the product

---

### Transport Tables

#### 9. `transport_mode`
Defines transportation methods.

| Column | Type | Description |
|--------|------|-------------|
| `transport_mode_id` | SERIAL PRIMARY KEY | Unique identifier |
| `name` | VARCHAR(50) NOT NULL UNIQUE | Transport mode name |

**Pre-seeded modes**:
- TRUCK
- RAIL
- BARGE
- PIPELINE

---

#### 10. `facility_transport_mode`
Junction table linking facilities to transport modes they support.

| Column | Type | Description |
|--------|------|-------------|
| `facility_id` | INT REFERENCES facility | Facility |
| `transport_mode_id` | INT REFERENCES transport_mode | Transport mode |
| `notes` | TEXT | Additional notes |

**Primary Key**: `(facility_id, transport_mode_id)`

---

### Parcel Data Tables

#### 11. `parcels`
Stores property parcel data with comprehensive property information and geospatial data. This table is typically populated from external parcel data sources (e.g., county assessor data).

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGINT PRIMARY KEY | Auto-generated unique identifier |
| `parcelnumb` | TEXT | Parcel number (unique) |
| `geoid` | TEXT | Geographic identifier |
| `owner` | TEXT | Property owner name |
| `usedesc` | TEXT | Property use description (e.g., 'Agricultural Use', 'Farm Homesite') |
| `county` | TEXT | County name |
| `state2` | TEXT | State code |
| `lat` | DOUBLE PRECISION | Latitude |
| `lon` | DOUBLE PRECISION | Longitude |
| `geom` | geometry(Point, 4326) | PostGIS point geometry |
| `ll_gisacre` | NUMERIC | GIS-calculated acres |
| `agval` | NUMERIC | Agricultural value |
| `parval` | NUMERIC | Total parcel value |
| ... | ... | (Many additional property attributes) |

**Key Features**:
- Comprehensive property data including ownership, valuation, and legal descriptions
- Geospatial support with PostGIS geometry column
- Indexed on `parcelnumb` (unique), `geoid`, `county/state`, and `geom` (spatial index)

**Indexes**:
- Primary key on `id`
- Unique index on `parcelnumb`
- B-tree indexes on `geoid`, `county/state`
- GIST spatial index on `geom`

---

#### 12. `parcels_rush_stg`
Staging table for importing Rush County parcel data before merging into the main `parcels` table. Has the same structure as `parcels` but without the `id` identity column and `geom` column.

**Purpose**: Allows bulk import and data validation before merging into production `parcels` table.

**Indexes**:
- Unique index on `parcelnumb`
- B-tree indexes on `geoid`, `county/state`

---

## Database Views

The database includes several views for common queries and analysis:

#### 1. `facility_with_names`
**Primary view for GeoServer and web applications** - Comprehensive facility view with all related data joined together.

This view joins the `facility`, `company`, and `facility_type` tables to provide a single source of truth for all facility information needed for map rendering. It eliminates the need for separate lookup queries or client-side joins.

**Key Features**:
- Includes company name (`company_name`) and company details (website, phone)
- Includes facility type name (`facility_type_name`) and type metadata (is_producer, is_consumer, is_storage)
- Contains all facility fields (address, location, contact info, etc.)
- Includes PostGIS geometry (`geom`) for spatial queries
- Uses LEFT JOINs to include facilities even if company or facility_type is missing

**Columns**: 
- Facility identifiers: `facility_id`, `name`, `description`, `status`
- Company info: `company_id`, `company_name`, `company_website_url`, `company_phone_main`
- Facility type info: `facility_type_id`, `facility_type_name`, `facility_type_description`, `facility_type_is_producer`, `facility_type_is_consumer`, `facility_type_is_storage`
- Address: `address_line1`, `address_line2`, `city`, `county`, `state`, `postal_code`
- Location: `latitude`, `longitude`, `geom`
- Metadata: `opened_year`, `closed_year`, `website_url`, `phone_main`, `email_main`, `notes`

**Recommended Use**: Configure GeoServer to use this view (`facility_with_names`) instead of the `facility` table as the data source for the `aginfo:facility` layer. This ensures all web applications receive complete, readable data without requiring additional lookups.

---

#### 2. `beaver_8_mile`
Shows all parcels within 8 miles of the Beaver Grain Corp facility (parcel ID 10746).

**Columns**: All columns from `parcels` table plus a `gid` row number.

**Use Case**: Identify all properties within the service area of the Beaver Grain facility.

---

#### 3. `beaver_8_mile_ag`
Shows agricultural parcels within 8 miles of the Beaver Grain Corp facility, including distance calculation.

**Columns**: All columns from `parcels` plus:
- `gid`: Row number
- `distance_miles`: Distance from facility in miles

**Filter**: Only includes parcels where `usedesc` is 'Agricultural Use' or 'Farm Homesite'.

**Use Case**: Identify agricultural customers within the service area.

---

#### 4. `facility_parcels_8mi`
Shows all parcels within 8 miles of active grain elevator facilities (United Ag Services companies).

**Columns**: All columns from both `facility` and `parcels` tables, plus:
- `gid`: Row number
- `facility_name`: Name of the facility
- `distance_miles`: Distance from facility in miles

**Filter**: 
- Active facilities only (`status = 'ACTIVE'`)
- Grain elevators only (`facility_type_id = 1`)
- United Ag Services companies (`company_id IN (1, 8)`)

**Use Case**: Identify all properties within service areas of grain elevator facilities.

---

#### 5. `facility_customers_8mi`
Aggregates parcel owners within 8 miles of facilities, grouped by facility and owner.

**Columns**:
- `facility_name`: Name of the facility
- `owner`: Parcel owner name
- `mailadd`, `mail_address2`, `mail_city`, `mail_state2`, `mail_zip`: Mailing address
- `total_ll_gisacre`: Sum of GIS acres for all parcels owned
- `parcel_count`: Number of parcels owned

**Use Case**: Generate customer lists for marketing or analysis.

---

#### 6. `facility_customers_8mi_ag`
Aggregates agricultural parcel owners within 8 miles of facilities, grouped by facility and owner.

**Columns**: Same as `facility_customers_8mi` plus:
- `facility_id`: Facility identifier

**Filter**: Only includes parcels where `usedesc` is 'Agricultural Use' or 'Farm Homesite'.

**Use Case**: Generate agricultural customer lists for marketing or analysis.

---

### Crop Data Views

#### 7. `crop_summary_by_region_year`
Complete crop data summary by region and year with crop details.

**Columns**: All columns from `crop_acres`, `region`, and `crop_type` tables.

**Use Case**: View all crop data for a region in a specific year.

---

#### 8. `crop_totals_by_region`
Total crop acres by region aggregated across all years.

**Columns**: Region info, crop info, `total_acres`, `years_count`, `first_year`, `last_year`.

**Use Case**: See total historical crop production by region.

---

#### 9. `crop_totals_by_year`
Total crop acres by year aggregated across all regions.

**Columns**: Year, crop info, `total_acres`, `regions_count`.

**Use Case**: See total crop production trends over time.

---

#### 10. `top_crops_by_region`
Ranked crops by acres for each region, ordered by most recent year.

**Columns**: Region info, year, crop info, acres, `rank`.

**Use Case**: Identify the most important crops for each region.

---

#### 11. `crop_trends_by_region`
Year-over-year crop acreage trends with change calculations.

**Columns**: Region info, crop info, year, acres, `previous_year_acres`, `change_acres`, `change_percent`.

**Use Case**: Analyze crop acreage trends and changes over time.

---

#### 12. `row_crops_by_region_year`
Filtered view showing only row crops (corn, soybeans, wheat, etc.).

**Columns**: Region info, year, crop info, acres.

**Filter**: Only crops where `is_row_crop = TRUE`.

**Use Case**: Focus analysis on major row crops.

---

## Entity Relationship Diagram

```
company (1) ────< (many) facility
                      │
                      ├───< (many) facility_contact
                      │
                      ├───< (many) facility_service ────> (many) service_type
                      │
                      ├───< (many) facility_product ────> (many) product
                      │
                      └───< (many) facility_transport_mode ────> (many) transport_mode

facility_type (1) ────< (many) facility

parcels (standalone table with geospatial relationships to facilities via views)

region (1) ────< (many) crop_acres ────> (many) crop_type

region (1) ────< (many) crop_acres ────> (many) crop_type
```

---

## Key Features

### PostGIS Integration

The database uses PostGIS for geospatial operations:

- **Geometry Column**: Each facility has a `geom` column (Point, SRID 4326) for spatial queries
- **Automatic Generation**: A trigger automatically creates geometry from latitude/longitude
- **Spatial Queries**: Use PostGIS functions like `ST_Distance`, `ST_Within`, `ST_Buffer` for spatial analysis

### Automatic Geometry Trigger

The `trg_facility_set_geom` trigger automatically populates the `geom` column when:
- A new facility is inserted with `latitude` and `longitude` but no `geom`
- A facility is updated with new `latitude`/`longitude` values

This ensures spatial data is always available for mapping and spatial queries.

---

## Example Queries

### Find all facilities within 50 miles of a point

```sql
SELECT 
    f.name,
    f.city,
    f.state,
    ST_Distance(
        f.geom::geography,
        ST_SetSRID(ST_MakePoint(-99.551400, 38.471820), 4326)::geography
    ) / 1609.34 AS distance_miles
FROM facility f
WHERE ST_DWithin(
    f.geom::geography,
    ST_SetSRID(ST_MakePoint(-99.551400, 38.471820), 4326)::geography,
    80467  -- 50 miles in meters
)
ORDER BY distance_miles;
```

### Find facilities that offer a specific service

```sql
SELECT 
    f.name,
    f.city,
    f.state,
    st.name AS service_name
FROM facility f
JOIN facility_service fs ON f.facility_id = fs.facility_id
JOIN service_type st ON fs.service_type_id = st.service_type_id
WHERE st.name = '24 Hr Fuel'
  AND f.status = 'ACTIVE';
```

### Find facilities by company with their products

```sql
SELECT 
    c.name AS company_name,
    f.name AS facility_name,
    f.city,
    p.name AS product_name,
    fp.flow_role,
    fp.usage_role
FROM company c
JOIN facility f ON c.company_id = f.company_id
JOIN facility_product fp ON f.facility_id = fp.facility_id
JOIN product p ON fp.product_id = p.product_id
WHERE c.name = 'United Ag Services'
ORDER BY f.name, p.name;
```

### Get facility details with all relationships

```sql
SELECT 
    f.name AS facility_name,
    c.name AS company_name,
    ft.name AS facility_type,
    f.latitude,
    f.longitude,
    f.status,
    -- Services
    STRING_AGG(DISTINCT st.name, ', ') AS services,
    -- Products
    STRING_AGG(DISTINCT p.name, ', ') AS products,
    -- Transport modes
    STRING_AGG(DISTINCT tm.name, ', ') AS transport_modes
FROM facility f
LEFT JOIN company c ON f.company_id = c.company_id
LEFT JOIN facility_type ft ON f.facility_type_id = ft.facility_type_id
LEFT JOIN facility_service fs ON f.facility_id = fs.facility_id
LEFT JOIN service_type st ON fs.service_type_id = st.service_type_id
LEFT JOIN facility_product fp ON f.facility_id = fp.facility_id
LEFT JOIN product p ON fp.product_id = p.product_id
LEFT JOIN facility_transport_mode ftm ON f.facility_id = ftm.facility_id
LEFT JOIN transport_mode tm ON ftm.transport_mode_id = tm.transport_mode_id
WHERE f.status = 'ACTIVE'
GROUP BY f.facility_id, f.name, c.name, ft.name, f.latitude, f.longitude, f.status;
```

### Find parcels within 8 miles of a facility

```sql
-- Using the facility_parcels_8mi view
SELECT 
    facility_name,
    owner,
    parcelnumb,
    usedesc,
    ll_gisacre,
    distance_miles
FROM facility_parcels_8mi
WHERE facility_name = 'Alexander'
ORDER BY distance_miles;
```

### Get customer list for a facility

```sql
-- Using the facility_customers_8mi_ag view (agricultural customers only)
SELECT 
    facility_name,
    owner,
    mailadd,
    mail_city,
    mail_state2,
    mail_zip,
    total_ll_gisacre,
    parcel_count
FROM facility_customers_8mi_ag
WHERE facility_name = 'Alexander'
ORDER BY total_ll_gisacre DESC;
```

### Find agricultural parcels near Beaver Grain facility

```sql
-- Using the beaver_8_mile_ag view
SELECT 
    owner,
    parcelnumb,
    usedesc,
    ll_gisacre,
    distance_miles
FROM beaver_8_mile_ag
ORDER BY distance_miles;
```

### View crop data by region and year

```sql
-- Using the crop_summary_by_region_year view
SELECT 
    region_name,
    year,
    crop_name,
    acres
FROM crop_summary_by_region_year
WHERE region_name = 'Rush County'
  AND year = 2024
ORDER BY acres DESC;
```

### Analyze crop trends over time

```sql
-- Using the crop_trends_by_region view
SELECT 
    region_name,
    crop_name,
    year,
    acres,
    change_acres,
    change_percent
FROM crop_trends_by_region
WHERE region_name = 'Rush County'
  AND crop_name = 'Corn'
ORDER BY year;
```

### Compare top crops across regions

```sql
-- Using the top_crops_by_region view
SELECT 
    region_name,
    crop_name,
    acres,
    rank
FROM top_crops_by_region
WHERE rank <= 5
  AND year = 2024
ORDER BY region_name, rank;
```

---

## Database Initialization

The database is initialized through SQL scripts in `db/init/`:

1. **01_enable_postgis.sql**: Enables PostGIS and PostGIS Topology extensions
2. **02_schema_aginfo.sql**: Creates all core facility/company tables, triggers, and seed data for lookup tables
3. **03_seed_united_ag_alexander.sql**: Example seed data for United Ag Services - Alexander location
4. **04_facility_view_with_names.sql**: Creates the `facility_with_names` view for GeoServer
5. **05_schema_parcels.sql**: Creates the `parcels` table for property parcel data
6. **06_schema_parcels_rush_stg.sql**: Creates the `parcels_rush_stg` staging table
7. **07_views_parcels.sql**: Creates views for parcel analysis and facility-customer relationships
8. **08_schema_crop_data.sql**: Creates crop data tables (`crop_type`, `region`, `crop_acres`)
9. **09_views_crop_data.sql**: Creates views for crop data analysis and trends

These scripts run automatically when the PostGIS container is first created.

---

## GeoServer Integration

The database is designed to work with GeoServer for map visualization:

- **Workspace**: `aginfo`
- **Recommended Layer Source**: `facility_with_names` (view) - **Use this view instead of the `facility` table**
- **Alternative Layer Source**: `facility` (table) - Only use if view is not available
- **Geometry Column**: `geom`
- **SRID**: 4326 (WGS84)

**Recommended Configuration**: 
GeoServer should be configured to use the `facility_with_names` view as the data source for the `aginfo:facility` layer. This view includes all company and facility type names pre-joined, eliminating the need for client-side lookups and ensuring consistent, readable data across all web applications.

**Benefits of using the view**:
- All related data (company names, facility type names) is included in a single query
- Reduces client-side processing and lookup complexity
- Ensures consistency across all applications
- Better performance by leveraging database joins
- Single source of truth for facility display data

---

## Migration Validation

Before applying schema changes to production, use the validation system to ensure data integrity:

### Quick Validation

```bash
# Pre-migration checks
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/01_pre_migration_checks.sql

# Post-migration checks  
docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/validate/02_post_migration_checks.sql
```

### Automated Validation

```bash
# Linux/Mac
./db/validate/validate_migration.sh db/init/08_schema_crop_data.sql

# Windows (PowerShell)
.\db\validate\validate_migration.ps1 -MigrationFile "db\init\08_schema_crop_data.sql"
```

The validation system checks:
- **Data Integrity**: Orphaned records, broken foreign keys
- **Data Validation**: Geometry validity, coordinate ranges
- **Constraint Integrity**: Foreign keys, unique constraints
- **Index Integrity**: Critical indexes exist
- **View Integrity**: All views are queryable
- **Record Counts**: Baseline comparison to detect data loss

See `db/validate/README.md` for full documentation.

---

## Maintenance Notes

- **Backups**: Regular backups of `db/data/` directory recommended
- **Migration Validation**: Always run validation checks before/after schema changes (see above)
- **Indexes**: Consider adding indexes on frequently queried columns:
  - `facility.status`
  - `facility.company_id`
  - `facility.facility_type_id`
  - Spatial index on `facility.geom` (GIST index)
- **Constraints**: Foreign key constraints ensure referential integrity
- **Unique Constraints**: Company names, facility type names, service/product names are unique

---

## Version History

- **v1.0**: Initial schema with 10 core tables, PostGIS integration, and automatic geometry triggers
- **v1.1**: Added `parcels` and `parcels_rush_stg` tables, plus 6 views for parcel analysis and facility-customer relationships
- **v1.2**: Added crop data tables (`crop_type`, `region`, `crop_acres`) and 6 views for CDL (Cropland Data Layer) analysis

