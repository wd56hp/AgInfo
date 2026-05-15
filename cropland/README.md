# CDL (Cropland Data Layer) Processing Pipeline

This directory contains tools for processing USDA NASS Cropland Data Layer (CDL) GeoTIFF files to extract crop acreage data by region.

## Overview

The pipeline processes CDL raster data using `rasterio` to:
- Load USDA CDL GeoTIFF files
- Treat pixel values as categorical crop codes
- Preserve CRS and transform metadata
- Extract crop acreage by region boundaries
- Import data into the AgInfo database

## Directory Structure

```
/cropland/
  ├── config.py              # Configuration settings
  ├── cdl_pipeline.py          # Main processing pipeline
  ├── inspect_cdl.py          # Utility to inspect CDL files
  ├── requirements.txt        # Python dependencies
  ├── /data/
  │   ├── /cdl/              # CDL GeoTIFF files (place here)
  │   ├── /boundaries/       # Region boundary GeoJSON files
  │   ├── /logs/             # Processing logs
  │   ├── /temp/             # Temporary files
  │   └── /code/             # Additional scripts
  └── /outputs/
      ├── /tables/           # Output CSV/JSON tables
      └── /maps/             # Output map visualizations
```

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure settings in `config.py`:
   - Database connection details
   - CDL file paths
   - Processing options

## Usage

### Inspect CDL Files

Before processing, inspect a CDL file to see its metadata and crop codes:

```bash
python inspect_cdl.py cdl_2020.tif
python inspect_cdl.py --all  # Inspect all CDL files
```

### Process CDL Data

Process a single year:
```bash
python cdl_pipeline.py --year 2020 --region counties.geojson
```

Process all configured years:
```bash
python cdl_pipeline.py --all-years --region region_of_interest.geojson
```

### Command Line Options

- `--year YYYY`: Process a specific year (e.g., 2020)
- `--all-years`: Process all years configured in `config.py`
- `--region FILE.geojson`: Region boundary GeoJSON file (default: counties.geojson)
- `--state-fips CODE`: State FIPS code (overrides config default)

## CDL File Format

CDL files are GeoTIFF rasters where:
- **Pixel values** = Categorical crop codes (e.g., 1=Corn, 5=Soybeans)
- **CRS**: Typically Albers Equal Area (EPSG:5070) or similar
- **Resolution**: 30m or 56m pixels
- **Data type**: Integer (uint8 or uint16)

### Downloading CDL Files

Download CDL GeoTIFF files from:
- [USDA NASS CDL](https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php)

File naming convention: `CDL_YYYY_STATE_XXX.tif`
- Example: `CDL_2020_20_001.tif` (Kansas 2020)

Place downloaded files in `/cropland/data/cdl/`

## Region Boundaries

Region boundaries should be provided as GeoJSON files in `/cropland/data/boundaries/`.

Each feature should have:
- `geometry`: Polygon or MultiPolygon
- `name` or `NAME`: Region name (used for output)
- `id` or `region_id` (optional): Region identifier

The pipeline will:
- Automatically detect CRS or assume WGS84 (EPSG:4326)
- Reproject to match CDL CRS if needed
- Process each region separately

## Processing Workflow

1. **Load CDL Raster**: Opens GeoTIFF with rasterio, preserves CRS/transform
2. **Load Regions**: Reads GeoJSON boundaries as GeoDataFrame
3. **Reproject**: Reprojects regions to match CDL CRS
4. **Clip & Extract**: For each region:
   - Clips raster to region boundary
   - Counts pixels by categorical crop code
   - Converts pixels to acres
5. **Export**: Saves results to CSV/JSON tables
6. **Import**: (Optional) Imports to AgInfo database

## Output Format

The pipeline generates crop data records with:
- `cdl_code`: USDA CDL crop code
- `pixel_count`: Number of pixels
- `acres`: Calculated acres (pixels × conversion factor)
- `region_name`: Region name from GeoJSON
- `crs`: Coordinate reference system
- `transform`: Affine transform parameters

## Configuration

Edit `config.py` to customize:

- **CDL_CONFIG**: Years, state FIPS, file patterns
- **REGION_CONFIG**: Default region type, CRS settings
- **PROCESSING_CONFIG**: Filters, minimum pixel counts
- **OUTPUT_CONFIG**: Output formats, map generation
- **DB_CONFIG**: Database connection (for import)

## Pixel to Acres Conversion

CDL uses Albers Equal Area projection with a standard conversion factor:
- **Conversion factor**: 0.222394 acres per pixel (30m resolution)
- This factor is configurable in `config.py`

## Crop Codes

CDL uses integer codes to represent crop types:
- 1 = Corn
- 5 = Soybeans
- 24 = Winter Wheat
- etc.

See the `crop_type` table in the AgInfo database for the full list of codes.

## Troubleshooting

### "CDL file not found"
- Check file is in `/cropland/data/cdl/`
- Verify filename matches pattern in `config.py`
- Use `inspect_cdl.py` to list available files

### "No regions found"
- Verify GeoJSON has valid features
- Check geometry is valid (use QGIS or similar)

### CRS Mismatch
- Pipeline automatically reprojects regions to match CDL CRS
- Check logs for reprojection details

## Dependencies

See `requirements.txt` for full list. Key packages:
- `rasterio`: GeoTIFF reading/writing
- `geopandas`: Geospatial data handling
- `numpy`: Numerical operations
- `shapely`: Geometry operations

## Related Documentation

- [CDL Import Guide](../../db/README_CDL_IMPORT.md)
- [Database Schema](../../db/SCHEMA.md)
