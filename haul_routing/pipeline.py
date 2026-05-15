"""End-to-end haul matrix: field centroids to facilities over OSM drive network."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from tqdm import tqdm

from haul_routing.data_loading import load_vector_layer
from haul_routing.db_export import write_geopackage_routes, write_postgis
from haul_routing.network import (
    assign_travel_times,
    combined_bounds,
    expand_bounds_miles,
    load_drive_graph,
    route_length_miles_along_path,
)
from haul_routing.router import (
    STATUS_NO_CANDIDATES,
    STATUS_NO_FACILITY_SNAP,
    STATUS_NO_FIELD_SNAP,
    STATUS_OK,
    crow_distance_miles,
    nearest_graph_node,
    route_result_from_predecessor,
    single_source_drive_times,
)
from haul_routing.speeds import load_speed_config, unload_minutes_from_config

logger = logging.getLogger(__name__)

# Columns written to routes_all CSV (used when a chunk has zero parcels / zero rows).
_ROUTES_ALL_COLUMNS: List[str] = [
    "field_id",
    "owner_name",
    "field_centroid_lon",
    "field_centroid_lat",
    "field_centroid_wkt",
    "unload_minutes",
    "facility_id",
    "facility_name",
    "crow_miles",
    "drive_miles",
    "drive_minutes_one_way",
    "one_way_drive_plus_unload_minutes",
    "total_minutes_two_way_plus_unload",
    "is_closest_facility",
    "status",
]


def build_nearest_from_routes_all(df_all: pd.DataFrame) -> pd.DataFrame:
    """One row per ``field_id``: best successful route, else first row for that field."""
    if df_all.empty:
        return pd.DataFrame(columns=_ROUTES_ALL_COLUMNS)
    nearest_rows: List[Dict[str, Any]] = []
    for fid, grp in df_all.groupby("field_id", sort=False):
        ok_sub = grp[grp["status"] == STATUS_OK].copy()
        if len(ok_sub) == 0:
            nearest_rows.append(grp.iloc[0].to_dict())
        else:
            best = ok_sub.sort_values(
                ["drive_minutes_one_way", "crow_miles"],
                na_position="last",
            ).iloc[0]
            nearest_rows.append(best.to_dict())
    df_nearest = pd.DataFrame(nearest_rows)
    if not df_nearest.empty:
        df_nearest["is_closest_facility"] = True
    return df_nearest


def project_default_speed_config_path(project_root: Optional[Path] = None) -> Path:
    """``aginfo/config/road_speeds.yaml`` relative to repo root (AgInfo)."""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]
    return project_root / "aginfo" / "config" / "road_speeds.yaml"


def _fallback_speed_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "road_speeds.yaml"


def resolve_speed_config(speed_config_path: Optional[Union[str, Path]]) -> Path:
    if speed_config_path is not None:
        return Path(speed_config_path)
    p = project_default_speed_config_path()
    if p.is_file():
        return p
    return _fallback_speed_config_path()


def _ensure_column(df: gpd.GeoDataFrame, primary: str, fallbacks: List[str]) -> str:
    if primary in df.columns:
        return primary
    for f in fallbacks:
        if f in df.columns:
            logger.info("Using column %r as %r", f, primary)
            return f
    raise ValueError(f"Missing required column (tried {primary!r} and fallbacks {fallbacks})")


def calculate_field_to_facility_routes(
    fields_path: Union[str, Path],
    facilities_path: Union[str, Path],
    output_all_routes_path: Union[str, Path],
    output_nearest_path: Optional[Union[str, Path]] = None,
    max_candidate_miles: float = 50,
    unload_minutes: Optional[float] = None,
    speed_config_path: Optional[Union[str, Path]] = None,
    network_bbox_buffer_miles: float = 10,
    osm_graph_path: Optional[Union[str, Path]] = None,
    fields_layer: Optional[str] = None,
    facilities_layer: Optional[str] = None,
    field_id_column: str = "field_id",
    owner_column: Optional[str] = "owner_name",
    facility_id_column: str = "facility_id",
    facility_name_column: str = "facility_name",
    field_id_modulus: Optional[int] = None,
    field_id_remainder: Optional[int] = None,
    append_all_csv: bool = False,
    write_nearest_csv: bool = True,
    postgis_url: Optional[str] = None,
    postgis_all_table: str = "haul_field_facility_routes_all",
    postgis_nearest_table: str = "haul_field_facility_routes_nearest",
    output_all_gpkg: Optional[Union[str, Path]] = None,
    output_nearest_gpkg: Optional[Union[str, Path]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute drive distance and time from each field centroid to candidate facilities.

    Parameters
    ----------
    fields_path, facilities_path :
        GeoPackage, Shapefile, or GeoJSON paths.
    output_all_routes_path, output_nearest_path :
        Output CSV paths. If ``write_nearest_csv`` is False, ``output_nearest_path`` may be omitted.
    max_candidate_miles :
        Great-circle prefilter for facility candidates (geodesic miles).
    unload_minutes :
        If None, read from speed YAML ``defaults.unload_minutes`` (else 30).
    speed_config_path :
        Defaults to ``aginfo/config/road_speeds.yaml`` if present, else package ``config/road_speeds.yaml``.
    network_bbox_buffer_miles :
        Extra padding around data extent when downloading OSM (or truncating a local graph).
    osm_graph_path :
        Optional GraphML or OSM XML; if None, OSMnx downloads by bounding box.
    postgis_url :
        Optional SQLAlchemy URL, e.g. ``postgresql://user:pass@host:15433/aginfo``.
    field_id_modulus, field_id_remainder :
        If set, keep only parcels where ``field_id % modulus == remainder`` (chunked runs).
    append_all_csv :
        If True, append to ``output_all_routes_path`` without header when the file already exists.
    write_nearest_csv :
        If False, skip writing the per-field nearest summary (use after merging all-route chunks).
    """
    if write_nearest_csv and output_nearest_path is None:
        raise ValueError("output_nearest_path is required when write_nearest_csv is True")
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    cfg_path = resolve_speed_config(speed_config_path)
    speeds_mph, extras = load_speed_config(cfg_path)
    unload_val = unload_minutes_from_config(extras, unload_minutes)

    fields = load_vector_layer(fields_path, fields_layer)
    facilities = load_vector_layer(facilities_path, facilities_layer)

    fid_col = _ensure_column(fields, field_id_column, ["id", "fid", "ID", "parcel_id", "PARCEL_ID"])
    fac_id_col = _ensure_column(
        facilities, facility_id_column, ["id", "facility_id", "FACILITY_ID"]
    )
    fac_name_col = _ensure_column(
        facilities, facility_name_column, ["name", "NAME", "facility_name"]
    )

    owner_col_resolved: Optional[str] = None
    if owner_column:
        if owner_column in fields.columns:
            owner_col_resolved = owner_column
        else:
            for c in ("owner", "owner_name", "OWNER", "owntype"):
                if c in fields.columns:
                    owner_col_resolved = c
                    logger.info("Using column %r for owner_name output", c)
                    break

    fields = fields.copy()
    if field_id_modulus is not None:
        if field_id_remainder is None:
            raise ValueError("field_id_remainder is required when field_id_modulus is set")
        mod = int(field_id_modulus)
        rem = int(field_id_remainder)
        if mod < 1:
            raise ValueError("field_id_modulus must be >= 1")
        ids = fields[fid_col].astype("int64")
        fields = fields.loc[ids % mod == rem].copy()
        logger.info(
            "Chunk: field_id %% %d == %d → %d parcels",
            mod,
            rem,
            len(fields),
        )

    if fields.empty:
        logger.warning("No parcels to route after filters; skipping OSM load and writing empty outputs.")
        df_all = pd.DataFrame(columns=_ROUTES_ALL_COLUMNS)
        df_nearest = build_nearest_from_routes_all(df_all)
        out_all = Path(output_all_routes_path)
        out_all.parent.mkdir(parents=True, exist_ok=True)
        if not (append_all_csv and out_all.exists() and out_all.stat().st_size > 0):
            df_all.to_csv(out_all, index=False)
            logger.info("Wrote %s (0 rows)", out_all)
        else:
            logger.info("Append mode: no rows for this chunk; leaving %s unchanged", out_all)
        if write_nearest_csv and output_nearest_path is not None and not append_all_csv:
            out_nn = Path(output_nearest_path)
            out_nn.parent.mkdir(parents=True, exist_ok=True)
            df_nearest.to_csv(out_nn, index=False)
            logger.info("Wrote %s (0 rows)", out_nn)
        elif append_all_csv and write_nearest_csv:
            logger.info("Skipping nearest CSV for empty chunk (use merge_haul_nearest.py after concat).")
        if postgis_url and not append_all_csv:
            write_postgis(df_all, postgis_url, postgis_all_table, if_exists="replace")
            if write_nearest_csv:
                write_postgis(df_nearest, postgis_url, postgis_nearest_table, if_exists="replace")
        elif postgis_url and append_all_csv:
            logger.warning(
                "PostGIS load skipped (append_all_csv=True). Merge CSV chunks, then merge_nearest + load once."
            )
        return df_all, df_nearest

    fields["__centroid"] = fields.geometry.centroid
    fields["__lon"] = fields["__centroid"].x
    fields["__lat"] = fields["__centroid"].y

    facilities = facilities.copy()
    facilities["__lon"] = facilities.geometry.x
    facilities["__lat"] = facilities.geometry.y

    flon = facilities["__lon"].to_numpy()
    flat = facilities["__lat"].to_numpy()
    fac_ids = facilities[fac_id_col].to_numpy()
    fac_names = facilities[fac_name_col].to_numpy()

    b = combined_bounds(fields, facilities)
    # Download graph for the extent of inputs plus a modest margin (snapping, rural connectors).
    # Do not add max_candidate_miles here—that only filters facility pairs and would force huge extracts.
    bbox = expand_bounds_miles(
        *b, buffer_miles=max(network_bbox_buffer_miles, 5.0)
    )
    logger.info("Loading OSM drive network for bbox %s", bbox)
    G = load_drive_graph(bbox, nx_osm_path=Path(osm_graph_path) if osm_graph_path else None)
    G = assign_travel_times(G, speeds_mph)
    logger.info("Projected graph: %d nodes, %d edges", len(G), G.number_of_edges())

    fac_nodes: List[Optional[int]] = []
    for j in range(len(facilities)):
        fac_nodes.append(nearest_graph_node(G, float(flon[j]), float(flat[j])))
    n_snap = sum(1 for x in fac_nodes if x is not None)
    logger.info("Snapped %d / %d facilities to drive network nodes", n_snap, len(facilities))

    all_rows: List[Dict[str, Any]] = []

    def field_row_base(
        field_key: Any,
        owner: Any,
        flon: float,
        flat: float,
    ) -> Dict[str, Any]:
        pt = Point(flon, flat)
        return {
            "field_id": field_key,
            "owner_name": owner,
            "field_centroid_lon": flon,
            "field_centroid_lat": flat,
            "field_centroid_wkt": pt.wkt,
            "unload_minutes": unload_val,
        }

    for idx in tqdm(range(len(fields)), desc="Fields"):
        row = fields.iloc[idx]
        fk = row[fid_col]
        owner = row[owner_col_resolved] if owner_col_resolved else None
        lon, lat = float(row["__lon"]), float(row["__lat"])

        base = field_row_base(fk, owner, lon, lat)
        dmi = crow_distance_miles(lon, lat, flon, flat)
        mask = dmi <= max_candidate_miles
        if not mask.any():
            all_rows.append(
                {
                    **base,
                    "facility_id": None,
                    "facility_name": None,
                    "crow_miles": None,
                    "drive_miles": None,
                    "drive_minutes_one_way": None,
                    "one_way_drive_plus_unload_minutes": None,
                    "total_minutes_two_way_plus_unload": None,
                    "is_closest_facility": False,
                    "status": STATUS_NO_CANDIDATES,
                }
            )
            continue

        field_node = nearest_graph_node(G, lon, lat)
        if field_node is None:
            for j in range(len(facilities)):
                if not mask[j]:
                    continue
                all_rows.append(
                    {
                        **base,
                        "facility_id": fac_ids[j],
                        "facility_name": fac_names[j],
                        "crow_miles": float(dmi[j]),
                        "drive_miles": None,
                        "drive_minutes_one_way": None,
                        "one_way_drive_plus_unload_minutes": None,
                        "total_minutes_two_way_plus_unload": None,
                        "is_closest_facility": False,
                        "status": STATUS_NO_FIELD_SNAP,
                    }
                )
            continue

        candidate_results: List[Dict[str, Any]] = []
        pred: Dict[Any, Any] = {}
        dist_time: Dict[Any, float] = {}
        computed_tree = False

        for j in range(len(facilities)):
            if not mask[j]:
                continue
            crow = float(dmi[j])
            fac_node = fac_nodes[j]
            row_d: Dict[str, Any] = {
                **base,
                "facility_id": fac_ids[j],
                "facility_name": fac_names[j],
                "crow_miles": crow,
                "is_closest_facility": False,
            }
            if fac_node is None:
                row_d.update(
                    {
                        "drive_miles": None,
                        "drive_minutes_one_way": None,
                        "one_way_drive_plus_unload_minutes": None,
                        "total_minutes_two_way_plus_unload": None,
                        "status": STATUS_NO_FACILITY_SNAP,
                    }
                )
                candidate_results.append(row_d)
                continue

            if not computed_tree:
                pred, dist_time = single_source_drive_times(G, field_node)
                computed_tree = True

            res = route_result_from_predecessor(
                G, pred, dist_time, field_node, fac_node, route_length_miles_along_path
            )
            if res.status != STATUS_OK:
                row_d.update(
                    {
                        "drive_miles": None,
                        "drive_minutes_one_way": None,
                        "one_way_drive_plus_unload_minutes": None,
                        "total_minutes_two_way_plus_unload": None,
                        "status": res.status,
                    }
                )
                candidate_results.append(row_d)
                continue

            ow = float(res.drive_minutes_one_way)
            row_d.update(
                {
                    "drive_miles": float(res.drive_miles),
                    "drive_minutes_one_way": ow,
                    "one_way_drive_plus_unload_minutes": ow + unload_val,
                    "total_minutes_two_way_plus_unload": 2.0 * ow + unload_val,
                    "status": STATUS_OK,
                }
            )
            candidate_results.append(row_d)

        # Closest by successful one-way drive time (tie-break: shorter crow-miles)
        ok = [c for c in candidate_results if c.get("status") == STATUS_OK]
        if ok:
            best = min(
                ok,
                key=lambda x: (float(x["drive_minutes_one_way"]), float(x["crow_miles"])),
            )
            for c in candidate_results:
                if c["facility_id"] == best["facility_id"]:
                    c["is_closest_facility"] = True
        all_rows.extend(candidate_results)

    df_all = pd.DataFrame(all_rows)
    df_nearest = build_nearest_from_routes_all(df_all)

    out_all = Path(output_all_routes_path)
    out_all.parent.mkdir(parents=True, exist_ok=True)
    if append_all_csv and out_all.exists() and out_all.stat().st_size > 0:
        df_all.to_csv(out_all, mode="a", header=False, index=False)
    else:
        df_all.to_csv(out_all, index=False)
    logger.info("Wrote %s (%d rows, append=%s)", out_all, len(df_all), append_all_csv)

    if write_nearest_csv:
        assert output_nearest_path is not None
        out_nn = Path(output_nearest_path)
        out_nn.parent.mkdir(parents=True, exist_ok=True)
        df_nearest.to_csv(out_nn, index=False)
        logger.info("Wrote %s (%d rows)", out_nn, len(df_nearest))

    if output_all_gpkg and not append_all_csv:
        write_geopackage_routes(df_all, output_all_gpkg, layer="all_routes")
    if output_nearest_gpkg and write_nearest_csv and not append_all_csv:
        write_geopackage_routes(df_nearest, output_nearest_gpkg, layer="nearest")

    if postgis_url and not append_all_csv:
        write_postgis(df_all, postgis_url, postgis_all_table, if_exists="replace")
        if write_nearest_csv:
            write_postgis(df_nearest, postgis_url, postgis_nearest_table, if_exists="replace")
    elif postgis_url and append_all_csv:
        logger.warning(
            "PostGIS load skipped (append_all_csv=True). Merge CSV chunks, then merge_nearest + load once."
        )

    return df_all, df_nearest
