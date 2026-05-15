"""Load vector inputs (GeoPackage, Shapefile, GeoJSON)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import geopandas as gpd
from pyproj import CRS

logger = logging.getLogger(__name__)

VECTOR_EXTENSIONS = {".gpkg", ".shp", ".geojson", ".json"}


def _detect_driver(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".gpkg":
        return "GPKG"
    if suf == ".shp":
        return "ESRI Shapefile"
    if suf in (".geojson", ".json"):
        return "GeoJSON"
    raise ValueError(f"Unsupported vector format: {path}")


def load_vector_layer(
    path: Union[str, Path],
    layer: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """
    Read a GeoDataFrame from path, reprojecting to EPSG:4326 if needed.

    For GeoPackage, pass ``layer`` when the file has multiple layers.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    driver = _detect_driver(path)
    kwargs = {}
    if layer and driver == "GPKG":
        kwargs["layer"] = layer

    gdf = gpd.read_file(path, driver=driver, **kwargs)
    if gdf.crs is None:
        logger.warning("Input %s has no CRS; assuming EPSG:4326", path)
        gdf = gdf.set_crs(4326)
    elif gdf.crs != CRS.from_epsg(4326):
        gdf = gdf.to_crs(4326)

    if gdf.empty:
        raise ValueError(f"No features loaded from {path}")

    geom_col = gdf.geometry.name
    if geom_col not in gdf.columns:
        raise ValueError("GeoDataFrame has no geometry column")

    invalid = ~gdf.geometry.notna()
    if invalid.any():
        n = int(invalid.sum())
        logger.warning("Dropping %d rows with null geometry from %s", n, path)
        gdf = gdf.loc[~invalid].copy()

    return gdf
