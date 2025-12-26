# CDL (Cropland Data Layer) Data Import Guide

This guide explains how to import federal crop data from USDA NASS Cropland Data Layer (CDL) into the AgInfo database.

## Overview

The CDL import process involves:
1. Downloading CDL GeoTIFF files by year and state
2. Processing rasters to extract crop acreage by region
3. Importing the results into the database

## Database Schema

The crop data is stored in three main tables:

### 1. `crop_type`
Lookup table for crop types with CDL codes. Pre-populated with common crops.

### 2. `region`
Geographical regions for analysis (counties, watersheds, custom polygons).

### 3. `crop_acres`
Main fact table storing: Region | Year | Crop | Acres

## Workflow

### Step 1: Download CDL Data

Download CDL GeoTIFF files from [USDA NASS](https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php):

- One GeoTIFF per state × year
- Example: `CDL_2024_20_001.tif` (Kansas 2024)
- Repeat for all years needed (e.g., 2015–2024)

### Step 2: Prepare Region Boundaries

Your "geographical region" can be:
- County
- Watershed
- Custom polygon
- State or multi-state region

**⚠️ Critical**: Reproject polygons to the CDL CRS (Albers Equal Area) to preserve area accuracy.

### Step 3: Process Raster Data

#### Option A: Using QGIS

1. **Clip raster to region**
   - Raster → Extraction → Clip Raster by Mask Layer
   - This speeds up processing

2. **Tabulate pixel counts by crop**
   - Raster → Zonal Histogram
   - Or: GRASS r.stats
   - Or: Processing → Raster layer unique values report
   
   This gives: `Crop_Code | Pixel_Count`

3. **Convert pixels → acres**
   ```
   Acres = Pixel_Count × 0.222394
   ```
   (Exact value depends on projection — Albers is consistent)

#### Option B: Using Python

```python
import rasterio
import geopandas as gpd
from rasterio.mask import mask
import numpy as np

# Load region boundary
region = gpd.read_file('county_boundary.shp')
region_geom = region.geometry.values[0]

# Load CDL raster
with rasterio.open('CDL_2024_20_001.tif') as src:
    # Clip to region
    out_image, out_transform = mask(src, [region_geom], crop=True)
    
    # Get unique values and counts
    unique, counts = np.unique(out_image, return_counts=True)
    
    # Convert to acres (assuming Albers projection)
    pixel_size = 0.222394  # acres per pixel
    crop_data = []
    for code, count in zip(unique, counts):
        if code > 0:  # Skip background
            acres = count * pixel_size
            crop_data.append({
                'cdl_code': int(code),
                'pixel_count': int(count),
                'acres': acres
            })
```

#### Option C: Using PostGIS Raster

For large-scale processing, you can load CDL rasters directly into PostGIS:

```sql
-- Load raster into PostGIS
raster2pgsql -s 4326 -I -C -M CDL_2024_20_001.tif -F -t 100x100 public.cdl_2024_20 | psql -d aginfo

-- Extract crop data using zonal statistics
-- (Requires PostGIS raster extension)
```

### Step 4: Import into Database

#### Create Region (if not exists)

```sql
-- Example: Create a county region
INSERT INTO region (region_type, name, state, county, geom)
VALUES (
    'COUNTY',
    'Rush County',
    'KS',
    'Rush',
    ST_GeomFromText('POLYGON(...)', 4326)  -- Your county boundary
)
ON CONFLICT (region_type, name, state, county) DO NOTHING
RETURNING region_id;
```

#### Import Crop Data

```sql
-- Example: Import crop data for Rush County, 2024
INSERT INTO crop_acres (region_id, crop_type_id, year, acres, pixel_count)
SELECT 
    r.region_id,
    ct.crop_type_id,
    2024 AS year,
    :acres AS acres,  -- From your processing
    :pixel_count AS pixel_count  -- From your processing
FROM region r
CROSS JOIN crop_type ct
WHERE r.name = 'Rush County'
  AND r.state = 'KS'
  AND ct.cdl_code = :cdl_code  -- From your processing
ON CONFLICT (region_id, crop_type_id, year) 
DO UPDATE SET 
    acres = EXCLUDED.acres,
    pixel_count = EXCLUDED.pixel_count,
    processing_date = CURRENT_TIMESTAMP;
```

#### Bulk Import Script

For importing multiple crops/years, use a script:

```python
import psycopg2
from psycopg2.extras import execute_values

# Connect to database
conn = psycopg2.connect(
    host='172.16.101.20',
    port=15433,
    database='aginfo',
    user='agadmin',
    password='your_password'
)
cur = conn.cursor()

# Your processed data (from Step 3)
crop_data = [
    {'cdl_code': 1, 'acres': 1250.5, 'pixel_count': 5623},  # Corn
    {'cdl_code': 5, 'acres': 890.2, 'pixel_count': 4001},   # Soybeans
    # ... more crops
]

region_id = 1  # Your region ID
year = 2024

# Get crop_type_id for each CDL code
for crop in crop_data:
    cur.execute("""
        INSERT INTO crop_acres (region_id, crop_type_id, year, acres, pixel_count)
        SELECT 
            %s,
            ct.crop_type_id,
            %s,
            %s,
            %s
        FROM crop_type ct
        WHERE ct.cdl_code = %s
        ON CONFLICT (region_id, crop_type_id, year) 
        DO UPDATE SET 
            acres = EXCLUDED.acres,
            pixel_count = EXCLUDED.pixel_count,
            processing_date = CURRENT_TIMESTAMP
    """, (region_id, year, crop['acres'], crop['pixel_count'], crop['cdl_code']))

conn.commit()
cur.close()
conn.close()
```

## Querying Crop Data

### View crop data by region and year

```sql
SELECT * FROM crop_summary_by_region_year
WHERE region_name = 'Rush County'
  AND year = 2024
ORDER BY acres DESC;
```

### Get top crops for a region

```sql
SELECT * FROM top_crops_by_region
WHERE region_name = 'Rush County'
  AND rank <= 10
ORDER BY year DESC, rank;
```

### Analyze crop trends

```sql
SELECT * FROM crop_trends_by_region
WHERE region_name = 'Rush County'
  AND crop_name = 'Corn'
ORDER BY year;
```

### Compare regions

```sql
SELECT 
    region_name,
    year,
    crop_name,
    acres
FROM crop_summary_by_region_year
WHERE crop_name IN ('Corn', 'Soybeans', 'Winter Wheat')
  AND year = 2024
ORDER BY region_name, acres DESC;
```

## Accuracy Notes

### What CDL measures well:
- Row crops (corn, soybeans, wheat)
- Large fields
- Year-over-year trends
- Regional totals

### What CDL does NOT measure well:
- Small specialty crops
- Intercropping
- Very small parcels (<30 m wide)
- Sub-field variability

**Important**: CDL is:
- Observed planting, not zoning
- Annual snapshot, not yield
- Accurate enough for policy, economics, planning

## Automation

For processing multiple years/regions, consider:

1. **Python script** with rasterio + geopandas
2. **PostGIS raster** for large-scale processing
3. **Google Earth Engine** (very popular for CDL)
4. **QGIS Processing Model** for repeatable workflows

## Resources

- [USDA NASS CDL](https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php)
- [CDL Metadata](https://www.nass.usda.gov/Research_and_Science/Cropland/metadata.php)
- [CDL Crop Codes](https://www.nass.usda.gov/Research_and_Science/Cropland/metadata/cropland_metadata.php)

