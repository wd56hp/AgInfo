# Parcels Tables and Views - Changelog

## Overview

This document describes the addition of parcel data tables and analysis views to the AgInfo database. These additions enable analysis of property parcels and their relationships to agricultural facilities.

## New Tables

### 1. `parcels` Table
- **File**: `db/init/05_schema_parcels.sql`
- **Purpose**: Stores comprehensive property parcel data with geospatial information
- **Key Features**:
  - 150+ columns covering property ownership, valuation, legal descriptions, and more
  - PostGIS geometry column (`geom`) for spatial queries
  - Auto-generated `id` primary key
  - Unique constraint on `parcelnumb`
  - Multiple indexes for performance (geoid, county/state, spatial index on geom)

### 2. `parcels_rush_stg` Table
- **File**: `db/init/06_schema_parcels_rush_stg.sql`
- **Purpose**: Staging table for importing Rush County parcel data
- **Key Features**:
  - Same structure as `parcels` but without `id` identity column and `geom` column
  - Allows bulk import and validation before merging into production table
  - Indexed for efficient lookups

## New Views

### 1. `beaver_8_mile`
- **File**: `db/init/07_views_parcels.sql`
- **Purpose**: All parcels within 8 miles of Beaver Grain Corp facility (parcel ID 10746)
- **Use Case**: Identify all properties within the service area

### 2. `beaver_8_mile_ag`
- **File**: `db/init/07_views_parcels.sql`
- **Purpose**: Agricultural parcels within 8 miles of Beaver Grain Corp facility
- **Features**: Includes distance calculation in miles
- **Filter**: Only 'Agricultural Use' or 'Farm Homesite' parcels

### 3. `facility_parcels_8mi`
- **File**: `db/init/07_views_parcels.sql`
- **Purpose**: All parcels within 8 miles of active grain elevator facilities
- **Filter**: 
  - Active facilities only
  - Grain elevators only (facility_type_id = 1)
  - United Ag Services companies (company_id IN (1, 8))
- **Features**: Includes distance calculation in miles

### 4. `facility_customers_8mi`
- **File**: `db/init/07_views_parcels.sql`
- **Purpose**: Aggregated customer list (parcel owners) within 8 miles of facilities
- **Aggregation**: Groups by facility and owner, sums acres, counts parcels
- **Output**: Mailing addresses and total acreage per owner

### 5. `facility_customers_8mi_ag`
- **File**: `db/init/07_views_parcels.sql`
- **Purpose**: Aggregated agricultural customer list within 8 miles of facilities
- **Filter**: Only agricultural parcels ('Agricultural Use' or 'Farm Homesite')
- **Features**: Includes facility_id for joining with facility data

## Installation

These tables and views are created automatically when the database is initialized, as the SQL files are in the `db/init/` directory and run in numerical order:

1. `05_schema_parcels.sql` - Creates parcels table
2. `06_schema_parcels_rush_stg.sql` - Creates staging table
3. `07_views_parcels.sql` - Creates all parcel analysis views

## Data Population

The `parcels` table is typically populated from external data sources (e.g., county assessor data). The `parcels_rush_stg` table is used as a staging area for Rush County data before merging into the main table.

## Usage Examples

See `db/README.md` for detailed usage examples and query patterns.

## Notes

- The views use hardcoded facility/parcel IDs (e.g., parcel ID 10746 for Beaver Grain). These may need to be parameterized in the future.
- Distance calculations use PostGIS geography functions for accurate measurements in meters/miles.
- The 8-mile radius is hardcoded in the views but can be easily modified if needed.

