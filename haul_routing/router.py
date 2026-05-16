"""Snap origins/destinations to the graph and compute shortest paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Geod
from shapely.geometry import Point

logger = logging.getLogger(__name__)

GEOD = Geod(ellps="WGS84")

STATUS_OK = "ok"
STATUS_NO_FIELD_SNAP = "no_field_road_connection"
STATUS_NO_FACILITY_SNAP = "no_facility_road_connection"
STATUS_NO_CANDIDATES = "no_facility_within_prefilter_miles"
STATUS_ROUTE_FAILED = "route_failed"


@dataclass
class RouteResult:
    drive_miles: float
    drive_minutes_one_way: float
    status: str


def lonlat_to_graph_xy(lon: float, lat: float, crs: Any) -> Tuple[float, float]:
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(crs)
    g = pt.geometry.iloc[0]
    return float(g.x), float(g.y)


def nearest_graph_node(G: nx.MultiDiGraph, lon: float, lat: float) -> Optional[int]:
    """Return nearest node id or None if snap fails."""
    try:
        crs = G.graph["crs"]
        x, y = lonlat_to_graph_xy(lon, lat, crs)
        node = ox.distance.nearest_nodes(G, x, y)
        if node is None or (isinstance(node, float) and np.isnan(node)):
            return None
        return int(node)
    except ImportError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("nearest_nodes failed: %s", e)
        return None


def nearest_graph_nodes_batch(
    G: nx.MultiDiGraph, lons: np.ndarray, lats: np.ndarray
) -> List[Optional[int]]:
    """Snap many lon/lat points to nearest graph nodes (one OSMnx call; faster than a Python loop)."""
    if len(lons) == 0:
        return []
    try:
        crs = G.graph["crs"]
        pts = gpd.GeoSeries.from_xy(x=lons, y=lats, crs="EPSG:4326").to_crs(crs)
        xs = pts.x.to_numpy(dtype=float)
        ys = pts.y.to_numpy(dtype=float)
        nodes = ox.distance.nearest_nodes(G, xs, ys)
        nodes = np.atleast_1d(np.asarray(nodes, dtype=object))
        out: List[Optional[int]] = []
        for n in nodes.flat:
            if n is None or (isinstance(n, float) and np.isnan(n)):
                out.append(None)
            else:
                out.append(int(n))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("nearest_nodes batch failed, falling back to sequential: %s", e)
        return [
            nearest_graph_node(G, float(lo), float(la)) for lo, la in zip(lons, lats)
        ]


def crow_distance_miles(
    field_lon: float,
    field_lat: float,
    fac_lon: np.ndarray,
    fac_lat: np.ndarray,
) -> np.ndarray:
    """Vectorized geodesic distance in miles."""
    n = len(fac_lon)
    fld_lon = np.full(n, field_lon, dtype=float)
    fld_lat = np.full(n, field_lat, dtype=float)
    _, _, dist_m = GEOD.inv(fld_lon, fld_lat, fac_lon.astype(float), fac_lat.astype(float))
    return dist_m / 1609.344


def single_source_drive_times(
    G: nx.MultiDiGraph, source: int
) -> Tuple[Dict[Any, Any], Dict[Any, float]]:
    """One Dijkstra tree: travel-time distance and predecessor map (for path rebuild)."""
    pred, dist = nx.dijkstra_predecessor_and_distance(G, source, weight="travel_time")
    return pred, dist


def reconstruct_path_predecessor(
    pred: Dict[Any, Any], source: Any, target: Any
) -> Optional[List[Any]]:
    """Rebuild node path from NetworkX predecessor dict (Dijkstra)."""
    if target == source:
        return [source]
    if target not in pred:
        return None
    path: List[Any] = []
    cur: Any = target
    seen: set[Any] = set()
    max_hops = len(pred) + 2
    hops = 0
    while cur != source:
        if cur in seen or hops > max_hops:
            return None
        seen.add(cur)
        hops += 1
        path.append(cur)
        p = pred.get(cur)
        if p is None:
            return None
        if isinstance(p, (list, tuple)):
            if not p:
                return None
            cur = p[0]
        else:
            cur = p
    path.append(source)
    path.reverse()
    return path


def route_result_from_predecessor(
    G: nx.MultiDiGraph,
    pred: Dict[Any, Any],
    dist_time: Dict[Any, float],
    source: int,
    dest: int,
    path_miles_fn: Any,
) -> RouteResult:
    if dest == source:
        return RouteResult(0.0, 0.0, STATUS_OK)
    t = dist_time.get(dest)
    if t is None:
        return RouteResult(float("nan"), float("nan"), STATUS_ROUTE_FAILED)
    path = reconstruct_path_predecessor(pred, source, dest)
    if path is None:
        try:
            path = nx.shortest_path(G, source, dest, weight="travel_time")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return RouteResult(float("nan"), float("nan"), STATUS_ROUTE_FAILED)
    miles = path_miles_fn(G, path)
    return RouteResult(float(miles), float(t), STATUS_OK)


def shortest_drive_route(
    G: nx.MultiDiGraph,
    orig: int,
    dest: int,
    path_miles_fn: Any,
) -> RouteResult:
    """Pairwise shortest time path (full graph search per call). Prefer batching via route_result_from_predecessor."""
    if orig == dest:
        return RouteResult(
            drive_miles=0.0,
            drive_minutes_one_way=0.0,
            status=STATUS_OK,
        )
    if not nx.has_path(G, orig, dest):
        return RouteResult(
            drive_miles=float("nan"),
            drive_minutes_one_way=float("nan"),
            status=STATUS_ROUTE_FAILED,
        )
    try:
        minutes = nx.shortest_path_length(G, orig, dest, weight="travel_time")
        path = nx.shortest_path(G, orig, dest, weight="travel_time")
        miles = path_miles_fn(G, path)
        return RouteResult(
            drive_miles=float(miles),
            drive_minutes_one_way=float(minutes),
            status=STATUS_OK,
        )
    except nx.NetworkXNoPath:
        return RouteResult(
            drive_miles=float("nan"),
            drive_minutes_one_way=float("nan"),
            status=STATUS_ROUTE_FAILED,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Routing exception: %s", e)
        return RouteResult(
            drive_miles=float("nan"),
            drive_minutes_one_way=float("nan"),
            status=STATUS_ROUTE_FAILED,
        )
