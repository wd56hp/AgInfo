"""
Configuration file for CDL (Cropland Data Layer) processing pipeline.
"""
import os
from pathlib import Path

# Base directory for the cropland project
BASE_DIR = Path(__file__).parent

# Data directories
DATA_DIR = BASE_DIR / "data"
CDL_DIR = DATA_DIR / "cdl"
BOUNDARIES_DIR = DATA_DIR / "boundaries"
LOGS_DIR = DATA_DIR / "logs"
TEMP_DIR = DATA_DIR / "temp"
CODE_DIR = DATA_DIR / "code"

# Output directories
OUTPUTS_DIR = BASE_DIR / "outputs"
TABLES_DIR = OUTPUTS_DIR / "tables"
MAPS_DIR = OUTPUTS_DIR / "maps"

# Database configuration
DB_CONFIG = {
    "host": "172.16.101.20",  # Update with your database host
    "port": 15433,  # Update with your database port
    "database": "aginfo",
    "user": "agadmin",
    "password": os.getenv("DB_PASSWORD", ""),  # Set via environment variable
}

# CDL processing configuration
CDL_CONFIG = {
    # Pixel to acres conversion factor (for Albers Equal Area projection)
    "pixel_to_acres": 0.222394,
    
    # Years to process
    "years": [2018, 2019, 2020],
    
    # State FIPS code (20 = Kansas, adjust as needed)
    "state_fips": 20,
    
    # CDL file naming pattern: CDL_YYYY_STATE_XXX.tif
    "cdl_filename_pattern": "CDL_{year}_{state_fips:02d}_001.tif",
}

# Region processing configuration
REGION_CONFIG = {
    # Default region type
    "default_region_type": "COUNTY",
    
    # Default state code
    "default_state": "KS",
    
    # CRS for processing (Albers Equal Area - EPSG:5070)
    "processing_crs": "EPSG:5070",
    
    # Output CRS (WGS84 - EPSG:4326)
    "output_crs": "EPSG:4326",
}

# Processing options
PROCESSING_CONFIG = {
    # Minimum pixel count to include in results (filters out noise)
    "min_pixel_count": 10,
    
    # Whether to skip background/water/developed areas
    "skip_non_crop": True,
    
    # Background CDL codes to skip (0 = background, 111 = water, etc.)
    "skip_cdl_codes": [0, 111, 121, 122, 123, 124, 131],
    
    # Logging level
    "log_level": "INFO",
}

# Output configuration
OUTPUT_CONFIG = {
    # Output format for tables (csv, json, parquet)
    "table_format": "csv",
    
    # Whether to generate maps
    "generate_maps": True,
    
    # Map output format (png, pdf, html)
    "map_format": "png",
    
    # Map DPI
    "map_dpi": 300,
}

# Ensure directories exist
for directory in [LOGS_DIR, TEMP_DIR, TABLES_DIR, MAPS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
