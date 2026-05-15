"""
CDL (Cropland Data Layer) Processing Pipeline

This script processes USDA NASS CDL GeoTIFF files to extract crop acreage
data by region and imports it into the AgInfo database.

Usage:
    python cdl_pipeline.py --year 2020 --region counties.geojson
    python cdl_pipeline.py --all-years --region region_of_interest.geojson
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json

import rasterio
from rasterio.mask import mask
import geopandas as gpd
import numpy as np
from shapely.geometry import mapping

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CDL_DIR, BOUNDARIES_DIR, LOGS_DIR, TEMP_DIR, TABLES_DIR, MAPS_DIR,
    DB_CONFIG, CDL_CONFIG, REGION_CONFIG, PROCESSING_CONFIG, OUTPUT_CONFIG
)

# Configure logging
log_file = LOGS_DIR / f"cdl_pipeline_{Path(__file__).stem}.log"
logging.basicConfig(
    level=getattr(logging, PROCESSING_CONFIG["log_level"]),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_region_boundaries(geojson_path: Path) -> Dict:
    """
    Load region boundaries from GeoJSON file.
    
    Args:
        geojson_path: Path to GeoJSON file containing region boundaries
        
    Returns:
        GeoJSON feature collection as dictionary
    """
    logger.info(f"Loading region boundaries from {geojson_path}")
    
    if not geojson_path.exists():
        raise FileNotFoundError(f"Region boundaries file not found: {geojson_path}")
    
    with open(geojson_path, 'r') as f:
        geojson_data = json.load(f)
    
    logger.info(f"Loaded {len(geojson_data.get('features', []))} region(s)")
    return geojson_data


def find_cdl_file(year: int, state_fips: int) -> Optional[Path]:
    """
    Find CDL GeoTIFF file for given year and state.
    
    Args:
        year: Year of CDL data
        state_fips: State FIPS code
        
    Returns:
        Path to CDL file if found, None otherwise
    """
    # Try exact filename pattern
    filename = CDL_CONFIG["cdl_filename_pattern"].format(
        year=year,
        state_fips=state_fips
    )
    filepath = CDL_DIR / filename
    
    if filepath.exists():
        return filepath
    
    # Try alternative naming patterns
    patterns = [
        f"CDL_{year}_{state_fips:02d}_001.tif",
        f"cdl_{year}.tif",
        f"CDL_{year}.tif",
    ]
    
    for pattern in patterns:
        filepath = CDL_DIR / pattern
        if filepath.exists():
            logger.info(f"Found CDL file with pattern: {pattern}")
            return filepath
    
    logger.warning(f"CDL file not found for year {year}, state FIPS {state_fips}")
    return None


def load_cdl_metadata(cdl_path: Path) -> Dict:
    """
    Load CDL GeoTIFF and extract metadata (CRS, transform, etc.).
    
    Args:
        cdl_path: Path to CDL GeoTIFF file
        
    Returns:
        Dictionary with raster metadata including:
        - crs: Coordinate reference system
        - transform: Affine transform
        - width, height: Raster dimensions
        - bounds: Raster bounding box
        - dtype: Data type
    """
    with rasterio.open(cdl_path) as src:
        metadata = {
            'crs': src.crs,
            'transform': src.transform,
            'width': src.width,
            'height': src.height,
            'bounds': src.bounds,
            'dtype': src.dtypes[0],
            'nodata': src.nodata,
            'count': src.count,
        }
        logger.info(f"CDL Metadata - CRS: {metadata['crs']}, "
                   f"Size: {metadata['width']}x{metadata['height']}, "
                   f"Bounds: {metadata['bounds']}")
        return metadata


def process_cdl_raster(cdl_path: Path, region_geojson: Dict) -> List[Dict]:
    """
    Process CDL raster to extract crop acreage by region.
    
    Uses rasterio to load USDA CDL GeoTIFF files, treating pixel values
    as categorical crop codes. Preserves CRS and transform metadata.
    
    Args:
        cdl_path: Path to CDL GeoTIFF file
        region_geojson: GeoJSON feature collection with region boundaries
        
    Returns:
        List of dictionaries with crop data: [{
            'cdl_code': int,
            'pixel_count': int,
            'acres': float,
            'region_name': str,
            'region_id': int (optional),
            'crs': str,
            'transform': tuple
        }]
    """
    logger.info(f"Processing CDL raster: {cdl_path}")
    
    # Load CDL metadata
    cdl_metadata = load_cdl_metadata(cdl_path)
    cdl_crs = cdl_metadata['crs']
    
    # Convert GeoJSON to GeoDataFrame
    gdf = gpd.GeoDataFrame.from_features(region_geojson['features'])
    
    if gdf.empty:
        logger.warning("No regions found in GeoJSON")
        return []
    
    # Ensure GeoDataFrame has CRS
    if gdf.crs is None:
        logger.info("GeoJSON has no CRS, assuming WGS84 (EPSG:4326)")
        gdf.set_crs('EPSG:4326', inplace=True)
    
    # Reproject regions to match CDL CRS if needed
    if gdf.crs != cdl_crs:
        logger.info(f"Reprojecting regions from {gdf.crs} to {cdl_crs}")
        gdf = gdf.to_crs(cdl_crs)
    
    # Get region name column (try common names)
    region_name_col = None
    for col in ['name', 'NAME', 'Name', 'region_name', 'county', 'COUNTY']:
        if col in gdf.columns:
            region_name_col = col
            break
    
    if region_name_col is None:
        logger.warning("No region name column found, using index")
        gdf['_region_name'] = gdf.index.astype(str)
        region_name_col = '_region_name'
    
    all_crop_data = []
    
    # Process each region
    with rasterio.open(cdl_path) as src:
        for idx, row in gdf.iterrows():
            region_geom = row.geometry
            region_name = str(row[region_name_col])
            
            logger.info(f"Processing region: {region_name}")
            
            # Clip raster to region boundary
            try:
                out_image, out_transform = mask(
                    src,
                    [mapping(region_geom)],
                    crop=True,
                    nodata=src.nodata
                )
            except Exception as e:
                logger.error(f"Error masking region {region_name}: {e}")
                continue
            
            # Extract pixel values (treat as categorical crop codes)
            # CDL rasters are single-band with integer crop codes
            pixel_data = out_image[0]  # First (and only) band
            
            # Filter out nodata values
            if src.nodata is not None:
                valid_pixels = pixel_data[pixel_data != src.nodata]
            else:
                valid_pixels = pixel_data.flatten()
            
            # Count pixels by categorical crop code
            unique_codes, pixel_counts = np.unique(valid_pixels, return_counts=True)
            
            # Process each crop code
            for cdl_code, pixel_count in zip(unique_codes, pixel_counts):
                cdl_code = int(cdl_code)
                
                # Skip background/non-crop codes if configured
                if PROCESSING_CONFIG["skip_non_crop"]:
                    if cdl_code in PROCESSING_CONFIG["skip_cdl_codes"]:
                        continue
                
                # Skip if below minimum pixel count
                if pixel_count < PROCESSING_CONFIG["min_pixel_count"]:
                    continue
                
                # Convert pixels to acres
                acres = convert_pixels_to_acres(pixel_count)
                
                crop_record = {
                    'cdl_code': cdl_code,
                    'pixel_count': int(pixel_count),
                    'acres': round(acres, 4),
                    'region_name': region_name,
                    'crs': str(cdl_crs),
                    'transform': tuple(out_transform)[:6],  # Affine transform parameters
                }
                
                # Add region_id if available
                if 'region_id' in row:
                    crop_record['region_id'] = int(row['region_id'])
                elif 'id' in row:
                    crop_record['region_id'] = int(row['id'])
                
                all_crop_data.append(crop_record)
            
            logger.info(f"Extracted {len([d for d in all_crop_data if d['region_name'] == region_name])} "
                       f"crop types for {region_name}")
    
    logger.info(f"Total crop records extracted: {len(all_crop_data)}")
    return all_crop_data


def convert_pixels_to_acres(pixel_count: int) -> float:
    """
    Convert pixel count to acres using CDL conversion factor.
    
    Args:
        pixel_count: Number of pixels
        
    Returns:
        Acres
    """
    return pixel_count * CDL_CONFIG["pixel_to_acres"]


def import_to_database(crop_data: List[Dict], year: int, region_name: str):
    """
    Import crop data into AgInfo database.
    
    This is a placeholder function. Actual implementation would:
    1. Connect to PostgreSQL database
    2. Get or create region record
    3. Insert/update crop_acres records
    
    Args:
        crop_data: List of crop data dictionaries
        year: Year of data
        region_name: Name of region
    """
    logger.info(f"Importing {len(crop_data)} crop records to database for {region_name}, {year}")
    logger.warning("This is a placeholder function. Implement database import.")
    
    # Placeholder implementation
    # Would use psycopg2 or SQLAlchemy to:
    # 1. Get region_id from region table
    # 2. For each crop:
    #    - Get crop_type_id from crop_type table using cdl_code
    #    - INSERT INTO crop_acres ... ON CONFLICT DO UPDATE


def export_to_table(crop_data: List[Dict], output_path: Path, format: str = "csv"):
    """
    Export crop data to table file (CSV, JSON, etc.).
    
    Args:
        crop_data: List of crop data dictionaries
        output_path: Path to output file
        format: Output format ('csv', 'json', 'parquet')
    """
    logger.info(f"Exporting crop data to {output_path} ({format} format)")
    
    if format == "csv":
        import csv
        if crop_data:
            with open(output_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=crop_data[0].keys())
                writer.writeheader()
                writer.writerows(crop_data)
    elif format == "json":
        with open(output_path, 'w') as f:
            json.dump(crop_data, f, indent=2)
    else:
        logger.warning(f"Unsupported output format: {format}")


def generate_map(crop_data: List[Dict], output_path: Path):
    """
    Generate visualization map of crop data.
    
    Args:
        crop_data: List of crop data dictionaries
        output_path: Path to output map file
    """
    logger.info(f"Generating map: {output_path}")
    logger.warning("This is a placeholder function. Implement map generation.")
    
    # Would use matplotlib, folium, or other mapping libraries


def process_year(year: int, region_file: str, state_fips: int = None):
    """
    Process CDL data for a single year.
    
    Args:
        year: Year to process
        region_file: Name of region GeoJSON file in boundaries directory
        state_fips: State FIPS code (defaults to config value)
    """
    logger.info(f"Processing CDL data for year {year}")
    
    # Load region boundaries
    region_path = BOUNDARIES_DIR / region_file
    region_geojson = load_region_boundaries(region_path)
    
    # Find CDL file
    state_fips = state_fips or CDL_CONFIG["state_fips"]
    cdl_path = find_cdl_file(year, state_fips)
    
    if not cdl_path:
        logger.error(f"CDL file not found for year {year}")
        return
    
    # Process raster
    crop_data = process_cdl_raster(cdl_path, region_geojson)
    
    if not crop_data:
        logger.warning(f"No crop data extracted for year {year}")
        return
    
    # Export to table
    output_filename = f"crop_data_{year}_{region_file.stem}.{OUTPUT_CONFIG['table_format']}"
    output_path = TABLES_DIR / output_filename
    export_to_table(crop_data, output_path, OUTPUT_CONFIG["table_format"])
    
    # Generate map if configured
    if OUTPUT_CONFIG["generate_maps"]:
        map_filename = f"crop_map_{year}_{region_file.stem}.{OUTPUT_CONFIG['map_format']}"
        map_path = MAPS_DIR / map_filename
        generate_map(crop_data, map_path)
    
    # Import to database
    region_name = region_path.stem
    import_to_database(crop_data, year, region_name)
    
    logger.info(f"Completed processing for year {year}")


def main():
    """Main entry point for CDL pipeline."""
    parser = argparse.ArgumentParser(
        description="Process USDA NASS CDL data and import to AgInfo database"
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Year to process (e.g., 2020)"
    )
    parser.add_argument(
        "--all-years",
        action="store_true",
        help="Process all years configured in config.py"
    )
    parser.add_argument(
        "--region",
        type=str,
        default="counties.geojson",
        help="Region GeoJSON file name (default: counties.geojson)"
    )
    parser.add_argument(
        "--state-fips",
        type=int,
        help="State FIPS code (overrides config default)"
    )
    
    args = parser.parse_args()
    
    # Determine years to process
    if args.all_years:
        years = CDL_CONFIG["years"]
    elif args.year:
        years = [args.year]
    else:
        logger.error("Must specify either --year or --all-years")
        parser.print_help()
        sys.exit(1)
    
    # Process each year
    for year in years:
        try:
            process_year(year, args.region, args.state_fips)
        except Exception as e:
            logger.error(f"Error processing year {year}: {e}", exc_info=True)
            continue
    
    logger.info("CDL pipeline completed")


if __name__ == "__main__":
    main()
