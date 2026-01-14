# AgInfo Database Schema Documentation

This document provides a comprehensive overview of the AgInfo PostgreSQL database schema, including all tables, views, relationships, and indexes.

## Table of Contents

1. [Overview](#overview)
2. [Core Schema (AgInfo)](#core-schema-aginfo)
3. [Parcels Schema](#parcels-schema)
4. [Crop Data Schema](#crop-data-schema)
5. [KGFA Schema](#kgfa-schema)
6. [Views](#views)
7. [Database Relationships](#database-relationships)
8. [Indexes](#indexes)
9. [Triggers and Functions](#triggers-and-functions)

---

## Overview

The AgInfo database is a PostgreSQL database with PostGIS extension for geospatial data. It stores information about agricultural facilities, companies, property parcels, crop data, and related information for agricultural business intelligence and mapping.

**Database Name:** `aginfo`  
**Extensions Required:** PostGIS  
**Default Schema:** `public`

---

## Core Schema (AgInfo)

The core schema manages companies, facilities, products, services, and related business information.

### Table: `company`

Stores company/organization information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `company_id` | SERIAL | PRIMARY KEY | Unique company identifier |
| `name` | VARCHAR(200) | NOT NULL, UNIQUE | Company name |
| `website_url` | VARCHAR(300) | | Company website URL |
| `phone_main` | VARCHAR(50) | | Main phone number |
| `notes` | TEXT | | Additional notes |

### Table: `facility_type`

Lookup table for facility types (e.g., Grain Elevator, Ethanol Plant).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `facility_type_id` | SERIAL | PRIMARY KEY | Unique facility type identifier |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Facility type name (e.g., 'Grain Elevator') |
| `description` | TEXT | | Description of facility type |
| `is_producer` | BOOLEAN | DEFAULT FALSE | Produces product |
| `is_consumer` | BOOLEAN | DEFAULT FALSE | Consumes product |
| `is_storage` | BOOLEAN | DEFAULT FALSE | Provides storage |

**Seed Data:**
- Grain Elevator (is_storage: TRUE)
- Ethanol Plant (is_consumer: TRUE, is_producer: TRUE)
- Feedlot (is_consumer: TRUE)
- Fertilizer Plant (is_storage: TRUE, is_consumer: TRUE)

### Table: `facility`

Main table storing facility/location information with geospatial data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `facility_id` | SERIAL | PRIMARY KEY | Unique facility identifier |
| `company_id` | INT | FOREIGN KEY → company(company_id) | Associated company |
| `facility_type_id` | INT | FOREIGN KEY → facility_type(facility_type_id) | Type of facility |
| `name` | VARCHAR(200) | NOT NULL | Facility name |
| `description` | TEXT | | Facility description |
| `address_line1` | VARCHAR(200) | | Street address line 1 |
| `address_line2` | VARCHAR(200) | | Street address line 2 |
| `city` | VARCHAR(100) | | City |
| `county` | VARCHAR(100) | | County |
| `state` | CHAR(2) | DEFAULT 'KS' | State code |
| `postal_code` | VARCHAR(20) | | ZIP/postal code |
| `latitude` | DECIMAL(9,6) | NOT NULL | Latitude coordinate |
| `longitude` | DECIMAL(9,6) | NOT NULL | Longitude coordinate |
| `geom` | geometry(Point, 4326) | | PostGIS point geometry (auto-generated from lat/lon) |
| `status` | VARCHAR(20) | DEFAULT 'ACTIVE' | Status: ACTIVE, INACTIVE, PLANNED |
| `opened_year` | SMALLINT | | Year facility opened |
| `closed_year` | SMALLINT | | Year facility closed |
| `website_url` | VARCHAR(300) | | Facility website URL |
| `phone_main` | VARCHAR(50) | | Main phone number |
| `email_main` | VARCHAR(200) | | Main email address |
| `notes` | TEXT | | Additional notes |

**Note:** The `geom` column is automatically populated from `latitude` and `longitude` via trigger `trg_facility_set_geom`.

### Table: `facility_contact`

Stores contact persons for facilities.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `contact_id` | SERIAL | PRIMARY KEY | Unique contact identifier |
| `facility_id` | INT | NOT NULL, FOREIGN KEY → facility(facility_id) | Associated facility |
| `name` | VARCHAR(200) | NOT NULL | Contact person name |
| `role_title` | VARCHAR(150) | | Job title/role (e.g., 'Location Manager') |
| `phone` | VARCHAR(50) | | Contact phone number |
| `email` | VARCHAR(200) | | Contact email address |
| `is_primary` | BOOLEAN | DEFAULT FALSE | Primary contact flag |
| `notes` | TEXT | | Additional notes |

### Table: `service_type`

Lookup table for service types offered by facilities.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `service_type_id` | SERIAL | PRIMARY KEY | Unique service type identifier |
| `name` | VARCHAR(150) | NOT NULL, UNIQUE | Service type name |
| `category` | VARCHAR(50) | | Category: 'GRAIN', 'FERTILIZER', 'FUEL', 'FEED', 'OTHER' |
| `description` | TEXT | | Service description |

### Table: `facility_service`

Junction table linking facilities to services they offer.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `facility_id` | INT | NOT NULL, FOREIGN KEY → facility(facility_id) | Facility identifier |
| `service_type_id` | INT | NOT NULL, FOREIGN KEY → service_type(service_type_id) | Service type identifier |
| `is_active` | BOOLEAN | DEFAULT TRUE | Service active status |
| `notes` | TEXT | | Additional notes |
| **PRIMARY KEY** | (facility_id, service_type_id) | | Composite primary key |

### Table: `product`

Lookup table for products (grain, fertilizer, fuel, etc.).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `product_id` | SERIAL | PRIMARY KEY | Unique product identifier |
| `name` | VARCHAR(150) | NOT NULL, UNIQUE | Product name (e.g., 'Wheat', 'NH3', 'Diesel') |
| `category` | VARCHAR(50) | | Category: 'GRAIN', 'FERTILIZER', 'FUEL', 'FEED', 'CHEMICAL', 'BYPRODUCT', 'OTHER' |
| `unit_default` | VARCHAR(20) | | Default unit: 'BU', 'GAL', 'TON' |
| `description` | TEXT | | Product description |

### Table: `facility_product`

Junction table linking facilities to products they handle.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `facility_id` | INT | NOT NULL, FOREIGN KEY → facility(facility_id) | Facility identifier |
| `product_id` | INT | NOT NULL, FOREIGN KEY → product(product_id) | Product identifier |
| `flow_role` | VARCHAR(20) | NOT NULL | Flow direction: 'INBOUND', 'OUTBOUND', 'BOTH' |
| `usage_role` | VARCHAR(20) | NOT NULL | Usage: 'CONSUMES', 'PRODUCES', 'STORES', 'RETAILS', 'HANDLES' |
| `is_bulk` | BOOLEAN | DEFAULT TRUE | Bulk handling flag |
| `notes` | TEXT | | Additional notes |
| **PRIMARY KEY** | (facility_id, product_id, flow_role, usage_role) | | Composite primary key |

### Table: `transport_mode`

Lookup table for transportation modes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `transport_mode_id` | SERIAL | PRIMARY KEY | Unique transport mode identifier |
| `name` | VARCHAR(50) | NOT NULL, UNIQUE | Mode name: 'TRUCK', 'RAIL', 'BARGE', 'PIPELINE' |

**Seed Data:** TRUCK, RAIL, BARGE, PIPELINE

### Table: `facility_transport_mode`

Junction table linking facilities to transportation modes they support.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `facility_id` | INT | NOT NULL, FOREIGN KEY → facility(facility_id) | Facility identifier |
| `transport_mode_id` | INT | NOT NULL, FOREIGN KEY → transport_mode(transport_mode_id) | Transport mode identifier |
| `notes` | TEXT | | Additional notes |
| **PRIMARY KEY** | (facility_id, transport_mode_id) | | Composite primary key |

---

## Parcels Schema

The parcels schema stores property parcel data with extensive geospatial and ownership information.

### Table: `parcels`

Main table for property parcel data with geospatial information.

**Key Columns:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGINT | PRIMARY KEY (auto-generated identity) |
| `geoid` | TEXT | Geographic identifier |
| `parcelnumb` | TEXT | Parcel number (indexed, unique) |
| `parcelnumb_no_formatting` | TEXT | Parcel number without formatting |
| `state_parcelnumb` | TEXT | State parcel number |
| `account_number` | TEXT | Tax account number |
| `tax_id` | TEXT | Tax ID |
| `usecode` | TEXT | Land use code |
| `usedesc` | TEXT | Land use description (e.g., 'Agricultural Use', 'Farm Homesite') |
| `zoning` | TEXT | Zoning code |
| `zoning_description` | TEXT | Zoning description |
| `yearbuilt` | INTEGER | Year structure was built |
| `owner` | TEXT | Owner name |
| `unmodified_owner` | TEXT | Original owner name |
| `ownfrst` | TEXT | Owner first name |
| `ownlast` | TEXT | Owner last name |
| `owner2`, `owner3`, `owner4` | TEXT | Additional owners |
| `previous_owner` | TEXT | Previous owner name |
| `mailadd` | TEXT | Mailing address |
| `mail_city` | TEXT | Mailing city |
| `mail_state2` | TEXT | Mailing state |
| `mail_zip` | TEXT | Mailing ZIP code |
| `address` | TEXT | Property address |
| `city` | TEXT | Property city |
| `county` | TEXT | County name |
| `state2` | TEXT | State code |
| `szip` | TEXT | Property ZIP code |
| `lat` | DOUBLE PRECISION | Latitude |
| `lon` | DOUBLE PRECISION | Longitude |
| `geom` | geometry(Point, 4326) | PostGIS point geometry |
| `deeded_acres` | NUMERIC | Deeded acres |
| `gisacre` | NUMERIC | GIS calculated acres |
| `sqft` | NUMERIC | Square feet |
| `ll_gisacre` | NUMERIC | LandLogic GIS acres |
| `parval` | NUMERIC | Total property value |
| `agval` | NUMERIC | Agricultural value |
| `landval` | NUMERIC | Land value |
| `improvval` | NUMERIC | Improvement value |
| `saleprice` | NUMERIC | Sale price |
| `saledate` | TEXT | Sale date |
| `taxamt` | NUMERIC | Tax amount |
| `taxyear` | INTEGER | Tax year |
| `census_tract` | TEXT | Census tract |
| `census_block` | TEXT | Census block |
| `census_blockgroup` | TEXT | Census block group |
| `census_zcta` | TEXT | Census ZIP code tabulation area |
| `plss_township` | TEXT | PLSS township |
| `plss_section` | TEXT | PLSS section |
| `plss_range` | TEXT | PLSS range |
| `legaldesc` | TEXT | Legal description |
| `totalagacres` | NUMERIC | Total agricultural acres |
| `totalagacresdr` | NUMERIC | Total ag acres dryland |
| `totalagacresir` | NUMERIC | Total ag acres irrigated |
| `totalagacresng` | NUMERIC | Total ag acres native grass |
| `totalagacrestg` | NUMERIC | Total ag acres tame grass |
| `totalacres` | NUMERIC | Total acres |

**Indexes:**
- `parcels_pkey` (PRIMARY KEY on `id`)
- `parcels_county_state_ix` (btree on `state2`, `county`)
- `parcels_geoid_ix` (btree on `geoid`)
- `parcels_geom_gix` (gist on `geom`)
- `parcels_parcelnumb_ix` (btree on `parcelnumb`)
- `parcels_parcelnumb_uidx` (unique btree on `parcelnumb`)

### Table: `parcels_rush_stg`

Staging table for Rush County parcel data import before merging into main `parcels` table.

**Structure:** Same as `parcels` table but without:
- `id` identity column
- `geom` column (geometry added during merge)

**Indexes:**
- `parcels_rush_stg_geoid_idx` (btree on `geoid`)
- `parcels_rush_stg_parcelnumb_idx` (btree on `parcelnumb`)
- `parcels_rush_stg_parcelnumb_idx1` (unique btree on `parcelnumb`)
- `parcels_rush_stg_state2_county_idx` (btree on `state2`, `county`)

---

## Crop Data Schema

The crop data schema stores Federal Crop Data Layer (CDL) information for crop acreage analysis.

### Table: `crop_type`

Lookup table for crop types with USDA NASS CDL codes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `crop_type_id` | SERIAL | PRIMARY KEY | Unique crop type identifier |
| `cdl_code` | INTEGER | NOT NULL, UNIQUE | USDA NASS CDL crop code (e.g., 1=Corn, 5=Soybeans) |
| `name` | VARCHAR(200) | NOT NULL, UNIQUE | Crop name (e.g., 'Corn', 'Soybeans') |
| `category` | VARCHAR(50) | | Category: 'GRAIN', 'OILSEED', 'FORAGE', 'VEGETABLE', 'FRUIT', 'OTHER' |
| `description` | TEXT | | Crop description |
| `is_row_crop` | BOOLEAN | DEFAULT FALSE | True for row crops (corn, soybeans, etc.) |
| `is_perennial` | BOOLEAN | DEFAULT FALSE | True for perennial crops (alfalfa, etc.) |
| `notes` | TEXT | | Additional notes |

**Seed Data:** Includes 100+ crop types with CDL codes (Corn, Soybeans, Winter Wheat, Spring Wheat, Alfalfa, Sorghum, etc.)

### Table: `region`

Defines geographical regions for crop data analysis (counties, watersheds, custom polygons).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `region_id` | SERIAL | PRIMARY KEY | Unique region identifier |
| `region_type` | VARCHAR(50) | NOT NULL | Type: 'COUNTY', 'WATERSHED', 'CUSTOM', 'STATE', 'MULTI_STATE' |
| `name` | VARCHAR(200) | NOT NULL | Region name (e.g., 'Rush County') |
| `state` | CHAR(2) | | State code |
| `county` | VARCHAR(100) | | County name (if region_type = 'COUNTY') |
| `description` | TEXT | | Region description |
| `geom` | geometry(Polygon, 4326) | | Region boundary polygon |
| `created_date` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | Creation timestamp |
| `notes` | TEXT | | Additional notes |
| **UNIQUE** | (region_type, name, state, county) | | Composite unique constraint |

**Indexes:**
- `region_geom_gix` (gist on `geom`)
- `region_type_ix` (btree on `region_type`)
- `region_state_county_ix` (btree on `state`, `county`)

### Table: `crop_acres`

Main fact table storing crop acreage data by region, year, and crop type.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `crop_acres_id` | SERIAL | PRIMARY KEY | Unique record identifier |
| `region_id` | INT | NOT NULL, FOREIGN KEY → region(region_id) | Region identifier |
| `crop_type_id` | INT | NOT NULL, FOREIGN KEY → crop_type(crop_type_id) | Crop type identifier |
| `year` | SMALLINT | NOT NULL | Year of CDL data (e.g., 2015, 2024) |
| `acres` | NUMERIC(12, 4) | NOT NULL | Acres of this crop in this region/year |
| `pixel_count` | BIGINT | | Original pixel count from CDL |
| `data_source` | VARCHAR(100) | DEFAULT 'USDA NASS CDL' | Source of data |
| `processing_date` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | When data was processed |
| `notes` | TEXT | | Additional notes |
| **UNIQUE** | (region_id, crop_type_id, year) | | One record per region/crop/year |

**Indexes:**
- `crop_acres_region_year_ix` (btree on `region_id`, `year`)
- `crop_acres_crop_year_ix` (btree on `crop_type_id`, `year`)
- `crop_acres_year_ix` (btree on `year`)

**Note:** Acres are calculated from CDL pixel counts (pixels × 0.222394 for Albers projection).

---

## KGFA Schema

The KGFA schema stores Kansas Grain and Feed Association member directory data.

### Table: `ksgfa_detail`

Stores member directory data from KGFA website.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `ksgfa_detail_id` | SERIAL | PRIMARY KEY | Unique record identifier |
| `company` | VARCHAR(200) | NOT NULL | Company/organization name |
| `contact` | VARCHAR(200) | | Contact person name (may be empty) |
| `phone` | VARCHAR(50) | | Phone number (may be empty) |
| `website` | VARCHAR(300) | | Website URL (may be empty) |
| `street` | VARCHAR(200) | | Street address (may be empty or contain placeholder) |
| `city` | VARCHAR(100) | | City (may be empty) |
| `state` | CHAR(2) | DEFAULT 'KS' | State code (defaults to KS) |
| `zip` | VARCHAR(20) | | ZIP/postal code (may be empty) |
| `notes` | TEXT | | Notes field (may contain HTML content) |
| `detail_url` | VARCHAR(500) | NOT NULL, UNIQUE | URL to detail page on KGFA website |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Update timestamp |

**Indexes:**
- `idx_ksgfa_detail_company` (btree on `company`)
- `idx_ksgfa_detail_location` (btree on `city`, `state`)
- `idx_ksgfa_detail_detail_url` (btree on `detail_url`)
- `idx_ksgfa_detail_zip` (btree on `zip`)

**Note:** This table serves as source data that can be merged into `company` and `facility` tables via script `11_merge_ksgfa_to_facilities.sql`.

---

## Views

### Facility Views

#### `facility_with_names`

Comprehensive view joining facility data with company and facility type names. Used by GeoServer and web applications.

**Columns:** All facility columns plus:
- `company_name`
- `company_website_url`
- `company_phone_main`
- `facility_type_name`
- `facility_type_description`
- `facility_type_is_producer`
- `facility_type_is_consumer`
- `facility_type_is_storage`

### Parcel Views

#### `beaver_8_mile`

All parcels within 8 miles of Beaver Grain Corp facility (parcel ID 10746).

**Columns:** All parcel columns from `parcels` table.

#### `beaver_8_mile_ag`

Agricultural parcels within 8 miles of Beaver Grain Corp facility with distance calculation.

**Columns:** All parcel columns plus `distance_miles` (calculated distance in miles).

**Filter:** `usedesc IN ('Agricultural Use', 'Farm Homesite')`

#### `facility_parcels_8mi`

All parcels within 8 miles of active grain elevator facilities (United Ag Services).

**Columns:** All parcel columns plus:
- `facility_id`
- `facility_name`
- `company_id`
- `facility_type_id`
- `distance_miles`

**Filter:** Active facilities with `company_id IN (1, 8)` and `facility_type_id = 1` (Grain Elevator).

#### `facility_customers_8mi`

Aggregated customer list (parcel owners) within 8 miles of facilities, grouped by facility and owner.

**Columns:**
- `facility_name`
- `owner`
- `mailadd`, `mail_address2`, `mail_city`, `mail_state2`, `mail_zip`
- `total_ll_gisacre` (sum of acres)
- `parcel_count`

#### `facility_customers_8mi_ag`

Aggregated agricultural customer list (parcel owners) within 8 miles of facilities.

**Columns:** Same as `facility_customers_8mi` plus `facility_id`.

**Filter:** `usedesc IN ('Agricultural Use', 'Farm Homesite')`

### Crop Data Views

#### `crop_summary_by_region_year`

Complete crop data summary by region and year with crop details.

**Columns:**
- `region_id`, `region_type`, `region_name`, `state`, `county`
- `year`
- `cdl_code`, `crop_name`, `crop_category`
- `acres`, `pixel_count`, `data_source`, `processing_date`

**Ordered by:** region name, year (DESC), acres (DESC)

#### `crop_totals_by_region`

Total acres by crop for each region (aggregated across all years).

**Columns:**
- `region_id`, `region_type`, `region_name`, `state`, `county`
- `cdl_code`, `crop_name`, `crop_category`
- `total_acres` (sum)
- `years_count`, `first_year`, `last_year`

#### `crop_totals_by_year`

Total acres by crop for each year (aggregated across all regions).

**Columns:**
- `year`
- `cdl_code`, `crop_name`, `crop_category`
- `total_acres` (sum)
- `regions_count`

#### `top_crops_by_region`

Ranked crops by acres for each region, ordered by most recent year.

**Columns:**
- `region_id`, `region_name`, `state`, `county`
- `year`
- `cdl_code`, `crop_name`, `crop_category`
- `acres`
- `rank` (ROW_NUMBER partitioned by region)

#### `crop_trends_by_region`

Year-over-year crop acreage trends with change calculations.

**Columns:**
- `region_id`, `region_name`, `state`, `county`
- `cdl_code`, `crop_name`
- `year`, `acres`
- `previous_year_acres`
- `change_acres` (difference)
- `change_percent` (percentage change)

#### `row_crops_by_region_year`

Row crops only (corn, soybeans, wheat, etc.) by region and year.

**Columns:**
- `region_id`, `region_name`, `state`, `county`
- `year`
- `cdl_code`, `crop_name`
- `acres`

**Filter:** `is_row_crop = TRUE`

---

## Database Relationships

### Core Schema Relationships

```
company (1) ──< (many) facility
facility_type (1) ──< (many) facility
facility (1) ──< (many) facility_contact
facility (many) ──< (many) service_type [via facility_service]
facility (many) ──< (many) product [via facility_product]
facility (many) ──< (many) transport_mode [via facility_transport_mode]
```

### Crop Data Relationships

```
region (1) ──< (many) crop_acres
crop_type (1) ──< (many) crop_acres
```

### KGFA Integration

The `ksgfa_detail` table is a source table that can be merged into the core schema:
- `ksgfa_detail.company` → `company.name`
- `ksgfa_detail` records → `facility` records (via merge script)
- `ksgfa_detail.contact` → `facility_contact.name`

### Parcels Relationships

The `parcels` table is standalone but can be spatially joined with `facility` using PostGIS functions (e.g., `ST_DWithin` for proximity analysis).

---

## Indexes

### Core Schema Indexes

- **facility:** Spatial index on `geom` (gist)
- **facility:** Index on `company_id`, `facility_type_id`
- **facility_contact:** Index on `facility_id`

### Parcels Indexes

- **parcels:**
  - Primary key on `id`
  - Unique index on `parcelnumb`
  - B-tree index on `geoid`
  - B-tree index on `state2`, `county`
  - GIST spatial index on `geom`

- **parcels_rush_stg:**
  - Unique index on `parcelnumb`
  - B-tree indexes on `geoid`, `state2`, `county`

### Crop Data Indexes

- **region:**
  - GIST spatial index on `geom`
  - B-tree indexes on `region_type`, `state`, `county`

- **crop_acres:**
  - B-tree indexes on `region_id`, `year`
  - B-tree indexes on `crop_type_id`, `year`
  - B-tree index on `year`

### KGFA Indexes

- **ksgfa_detail:**
  - B-tree indexes on `company`, `city`, `state`, `zip`, `detail_url`

---

## Triggers and Functions

### Function: `facility_set_geom()`

**Purpose:** Automatically sets the `geom` column (PostGIS point) from `latitude` and `longitude` when inserting or updating facility records.

**Trigger:** `trg_facility_set_geom`
- **Event:** BEFORE INSERT OR UPDATE
- **Table:** `facility`
- **Action:** Sets `geom` to `ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)` if `geom` is NULL and both coordinates are provided.

**Usage:** Ensures spatial geometry is always available for GIS operations even when only lat/lon are provided.

---

## Notes

1. **PostGIS Extension:** The database requires PostGIS extension (enabled in `01_enable_postgis.sql`).

2. **Spatial Reference System:** All geometry columns use SRID 4326 (WGS84).

3. **Data Import:** Parcel data is typically imported from external sources via SQL files in `db/temp/` directory.

4. **KGFA Merge:** The `11_merge_ksgfa_to_facilities.sql` script merges KGFA member directory data into the core facility and company tables.

5. **Crop Data:** Crop acreage data is calculated from USDA NASS CDL pixel counts using the conversion factor 0.222394 acres per pixel (for Albers projection).

6. **Distance Calculations:** Views use `ST_DWithin` and `ST_Distance` with geography casting for accurate distance calculations in meters/miles.

---

## Schema Initialization Order

The schema files in `db/init/` should be run in this order:

1. `01_enable_postgis.sql` - Enable PostGIS extension
2. `02_schema_aginfo.sql` - Core AgInfo schema
3. `03_seed_united_ag_alexander.sql` - Seed data (optional)
4. `04_facility_view_with_names.sql` - Facility views
5. `05_schema_parcels.sql` - Parcels schema
6. `06_schema_parcels_rush_stg.sql` - Parcels staging table
7. `07_views_parcels.sql` - Parcel views
8. `08_schema_crop_data.sql` - Crop data schema
9. `09_views_crop_data.sql` - Crop data views
10. `10_schema_ksgfa_detail.sql` - KGFA schema
11. `11_merge_ksgfa_to_facilities.sql` - KGFA merge script (optional)

---

*Last Updated: Generated from schema files in `db/init/`*
