"""Export haul routing results to PostGIS and GeoPackage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry import Point

logger = logging.getLogger(__name__)


def _add_point_geometry(df: pd.DataFrame, lon_col: str, lat_col: str) -> gpd.GeoDataFrame:
    geom = [
        Point(float(lo), float(la)) if pd.notna(lo) and pd.notna(la) else None
        for lo, la in zip(df[lon_col], df[lat_col])
    ]
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def write_geopackage_routes(
    df: pd.DataFrame,
    path: Union[str, Path],
    lon_col: str = "field_centroid_lon",
    lat_col: str = "field_centroid_lat",
    layer: str = "haul_routes",
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = _add_point_geometry(df, lon_col, lat_col)
    gdf.to_file(path, driver="GPKG", layer=layer)


def write_postgis(
    df: pd.DataFrame,
    engine_url: str,
    table_name: str,
    if_exists: str = "replace",
    geometry_column: str = "geom",
) -> None:
    """
    Write routes to PostGIS using GeoPandas ``to_postgis``.

    Uses ``field_centroid_wkt`` if present, otherwise ``field_centroid_lon`` / ``field_centroid_lat``.
    """
    try:
        from sqlalchemy import create_engine
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("sqlalchemy is required for PostGIS export") from e

    out = df.copy()
    if "field_centroid_wkt" in out.columns:
        geom = [
            wkt.loads(w) if pd.notna(w) and w else None for w in out["field_centroid_wkt"]
        ]
        gdf = gpd.GeoDataFrame(
            out.drop(columns=["field_centroid_wkt"]),
            geometry=geom,
            crs="EPSG:4326",
        )
    elif "field_centroid_lon" in out.columns and "field_centroid_lat" in out.columns:
        gdf = _add_point_geometry(out, "field_centroid_lon", "field_centroid_lat")
    else:
        raise ValueError("Need field_centroid_wkt or lon/lat columns for PostGIS geometry")

    gdf = gdf.rename_geometry(geometry_column)
    engine = create_engine(engine_url)
    gdf.to_postgis(table_name, engine, if_exists=if_exists, index=False)
    logger.info("Wrote %d rows to PostGIS table %s", len(gdf), table_name)
