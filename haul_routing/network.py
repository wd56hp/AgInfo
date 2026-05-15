"""Build a routable drive network from OSM (download or file) and assign travel times."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import geopandas as gpd
import networkx as nx
import osmnx as ox

from haul_routing.speeds import edge_speed_mph, edge_travel_time_minutes

logger = logging.getLogger(__name__)


def configure_osmnx_cache(project_root: Optional[Path] = None) -> None:
    """
    Keep OSM / Overpass response cache under the repo (default ``haul_routing/osmnx_cache``).
    Set ``OSMNX_CACHE`` to override; set ``OSMNX_USE_CACHE=0`` to disable caching.
    """
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]
    default_dir = project_root / "haul_routing" / "osmnx_cache"
    cache_dir = Path(os.environ.get("OSMNX_CACHE", str(default_dir)))
    cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = str(cache_dir)
    use = os.environ.get("OSMNX_USE_CACHE", "1").lower() not in ("0", "false", "no")
    ox.settings.use_cache = use
    logger.info("OSMnx cache folder=%s use_cache=%s", cache_dir, use)


def combined_bounds(fields: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame) -> Tuple[float, float, float, float]:
    """Return lon/lat bounds (minx, miny, maxx, maxy) in WGS84."""
    all_geom = gpd.GeoSeries(
        list(fields.geometry) + list(facilities.geometry), crs=fields.crs
    )
    b = all_geom.total_bounds
    return float(b[0]), float(b[1]), float(b[2]), float(b[3])


def expand_bounds_miles(
    minx: float, miny: float, maxx: float, maxy: float, buffer_miles: float
) -> Tuple[float, float, float, float]:
    """Expand WGS84 bbox by buffer_miles (approximate)."""
    mid_lat = (miny + maxy) / 2.0
    lat_pad = buffer_miles / 69.0
    lon_pad = buffer_miles / (69.0 * max(0.2, math.cos(math.radians(mid_lat))))
    return minx - lon_pad, miny - lat_pad, maxx + lon_pad, maxy + lat_pad


def load_drive_graph(
    bbox_wgs84: Tuple[float, float, float, float],
    nx_osm_path: Optional[Path] = None,
    network_type: str = "drive",
) -> nx.MultiDiGraph:
    """
    Load an OSM drive network.

    bbox_wgs84 : (west, south, east, north) decimal degrees.

    nx_osm_path : optional GraphML from OSMnx (``ox.save_graphml``) or .osm XML if supported.
    """
    west, south, east, north = bbox_wgs84
    configure_osmnx_cache()
    if nx_osm_path is not None:
        path = Path(nx_osm_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        suf = path.suffix.lower()
        if suf == ".graphml":
            G = ox.load_graphml(path)
        elif suf in (".osm", ".xml"):
            gxml = getattr(ox, "graph_from_xml", None)
            if gxml is None:
                raise ValueError(
                    "This OSMnx version has no graph_from_xml; use GraphML or leave osm_graph_path unset."
                )
            G = gxml(path, simplify=True, retain_all=False)
        else:
            raise ValueError(f"Unsupported network file type: {path}")

        trunc = getattr(ox.truncate, "truncate_graph_bbox", None) if hasattr(ox, "truncate") else None
        if trunc is None:
            trunc = getattr(ox, "truncate_graph_bbox", None)
        if callable(trunc):
            G = trunc(G, north, south, east, west, truncate_by_edge=True)
        else:
            logger.warning("OSMnx truncate_graph_bbox not found; using full graph from file (may be large).")
    else:
        try:
            G = ox.graph_from_bbox(
                bbox=(west, south, east, north),
                network_type=network_type,
                simplify=True,
                retain_all=False,
            )
        except TypeError:
            G = ox.graph_from_bbox(
                north,
                south,
                east,
                west,
                network_type=network_type,
                simplify=True,
                retain_all=False,
            )

    if len(G) == 0:
        raise RuntimeError(
            "OSM network is empty for the requested bbox; expand network_bbox_buffer_miles or supply a larger extract."
        )
    return G


def assign_travel_times(G: nx.MultiDiGraph, speeds_mph: dict[str, float]) -> nx.MultiDiGraph:
    """Add ``travel_time`` (minutes) and ``speed_mph`` on projected edge lengths."""
    Gp = ox.project_graph(G.copy())
    for _u, _v, _k, data in Gp.edges(keys=True, data=True):
        length_m = float(data.get("length", 0.0) or 0.0)
        mph = edge_speed_mph(data, speeds_mph)
        data["speed_mph"] = mph
        data["travel_time"] = edge_travel_time_minutes(length_m, mph)
    return Gp


def route_length_miles_along_path(G: nx.MultiDiGraph, path: list[Any]) -> float:
    """Sum edge ``length`` (meters) along a node path in a projected graph."""
    if len(path) < 2:
        return 0.0
    total_m = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edges = G.get_edge_data(u, v)
        if not edges:
            continue
        best_len = None
        best_tt: Optional[float] = None
        for _ek, d in edges.items():
            tt = d.get("travel_time")
            ln = float(d.get("length", 0.0) or 0.0)
            if best_tt is None or (tt is not None and tt < best_tt):
                best_tt = float(tt) if tt is not None else best_tt
                best_len = ln
        if best_len is not None:
            total_m += best_len
    return total_m / 1609.344
