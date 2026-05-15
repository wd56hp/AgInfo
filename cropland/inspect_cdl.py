"""
Utility script to inspect CDL GeoTIFF files and display metadata.

Usage:
    python inspect_cdl.py cdl_2020.tif
    python inspect_cdl.py --all
"""
import argparse
import sys
from pathlib import Path
import rasterio
import numpy as np

from config import CDL_DIR


def inspect_cdl_file(cdl_path: Path):
    """
    Inspect a CDL GeoTIFF file and display metadata and statistics.
    
    Args:
        cdl_path: Path to CDL GeoTIFF file
    """
    if not cdl_path.exists():
        print(f"Error: File not found: {cdl_path}")
        return
    
    print(f"\n{'='*60}")
    print(f"CDL File: {cdl_path.name}")
    print(f"{'='*60}\n")
    
    with rasterio.open(cdl_path) as src:
        # Basic metadata
        print("Raster Metadata:")
        print(f"  CRS: {src.crs}")
        print(f"  Dimensions: {src.width} x {src.height} pixels")
        print(f"  Bounds: {src.bounds}")
        print(f"  Transform: {src.transform}")
        print(f"  Data type: {src.dtypes[0]}")
        print(f"  NoData value: {src.nodata}")
        print(f"  Bands: {src.count}")
        
        # Read a sample of the data to get statistics
        print("\nReading raster data...")
        data = src.read(1)  # Read first band
        
        # Filter out nodata
        if src.nodata is not None:
            valid_data = data[data != src.nodata]
        else:
            valid_data = data.flatten()
        
        # Statistics
        print("\nPixel Value Statistics:")
        print(f"  Total pixels: {data.size:,}")
        print(f"  Valid pixels: {len(valid_data):,}")
        if src.nodata is not None:
            print(f"  NoData pixels: {(data == src.nodata).sum():,}")
        
        # Crop code statistics
        unique_codes, counts = np.unique(valid_data, return_counts=True)
        print(f"\nCrop Codes Found: {len(unique_codes)} unique codes")
        print(f"\nTop 20 Crop Codes (by pixel count):")
        print(f"{'CDL Code':<12} {'Pixel Count':<15} {'Percentage':<12}")
        print("-" * 40)
        
        # Sort by count descending
        sorted_indices = np.argsort(counts)[::-1]
        total_valid = len(valid_data)
        
        for idx in sorted_indices[:20]:
            code = int(unique_codes[idx])
            count = int(counts[idx])
            pct = (count / total_valid) * 100
            print(f"{code:<12} {count:<15,} {pct:<12.2f}%")
        
        if len(unique_codes) > 20:
            print(f"\n... and {len(unique_codes) - 20} more crop codes")
        
        # Pixel value range
        print(f"\nPixel Value Range:")
        print(f"  Minimum: {int(valid_data.min())}")
        print(f"  Maximum: {int(valid_data.max())}")
        print(f"  Mean: {valid_data.mean():.2f}")
        print(f"  Median: {np.median(valid_data):.2f}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Inspect CDL GeoTIFF files and display metadata"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="CDL GeoTIFF file to inspect (relative to CDL_DIR or absolute path)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Inspect all CDL files in CDL_DIR"
    )
    parser.add_argument(
        "--dir",
        type=str,
        help="Directory containing CDL files (default: from config)"
    )
    
    args = parser.parse_args()
    
    if args.all:
        # Inspect all CDL files
        cdl_dir = Path(args.dir) if args.dir else CDL_DIR
        cdl_files = list(cdl_dir.glob("*.tif")) + list(cdl_dir.glob("*.TIF"))
        
        if not cdl_files:
            print(f"No CDL files found in {cdl_dir}")
            return
        
        print(f"Found {len(cdl_files)} CDL file(s)\n")
        for cdl_file in sorted(cdl_files):
            inspect_cdl_file(cdl_file)
    
    elif args.file:
        # Inspect single file
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = CDL_DIR / file_path
        
        inspect_cdl_file(file_path)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
