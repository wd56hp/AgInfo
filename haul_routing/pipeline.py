"""End-to-end haul matrix: field centroids to facilities over OSM drive network."""

from __future__ import annotations

import logging
import multiprocessing
import sys
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
    nearest_graph_nodes_batch,
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


def _field_row_base_dict(
    field_key: Any,
    owner: Any,
    flon: float,
    flat: float,
    unload_val: float,
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


_FIELD_WORKER_CTX: Optional[Dict[str, Any]] = None


def _build_routes_for_field_index(idx: int, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute CSV rows for one field (all facility candidates). Used sequentially and in fork workers."""
    G = ctx["G"]
    fields = ctx["fields"]
    fid_col = ctx["fid_col"]
    owner_col_resolved: Optional[str] = ctx["owner_col_resolved"]
    flon = ctx["flon"]
    flat = ctx["flat"]
    fac_ids = ctx["fac_ids"]
    fac_names = ctx["fac_names"]
    fac_nodes: List[Optional[int]] = ctx["fac_nodes"]
    max_candidate_miles = float(ctx["max_candidate_miles"])
    unload_val = float(ctx["unload_val"])

    row = fields.iloc[idx]
    fk = row[fid_col]
    owner = row[owner_col_resolved] if owner_col_resolved else None
    lon, lat = float(row["__lon"]), float(row["__lat"])

    base = _field_row_base_dict(fk, owner, lon, lat, unload_val)
    dmi = crow_distance_miles(lon, lat, flon, flat)
    mask = dmi <= max_candidate_miles
    if not mask.any():
        return [
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
        ]

    field_node = nearest_graph_node(G, lon, lat)
    if field_node is None:
        out: List[Dict[str, Any]] = []
        for j in range(len(fac_ids)):
            if not mask[j]:
                continue
            out.append(
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
        return out

    candidate_results: List[Dict[str, Any]] = []
    pred: Dict[Any, Any] = {}
    dist_time: Dict[Any, float] = {}
    computed_tree = False

    nfac = len(fac_ids)
    for j in range(nfac):
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

    ok = [c for c in candidate_results if c.get("status") == STATUS_OK]
    if ok:
        best = min(
            ok,
            key=lambda x: (float(x["drive_minutes_one_way"]), float(x["crow_miles"])),
        )
        for c in candidate_results:
            if c["facility_id"] == best["facility_id"]:
                c["is_closest_facility"] = True
    return candidate_results


def _field_worker_entry(idx: int) -> List[Dict[str, Any]]:
    if _FIELD_WORKER_CTX is None:
        raise RuntimeError("field routing worker context is not initialized")
    return _build_routes_for_field_index(idx, _FIELD_WORKER_CTX)


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
    postgis_commit_every_n_fields: Optional[int] = 100,
    field_workers: int = 4,
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
    postgis_commit_every_n_fields :
        When ``postgis_url`` is set and ``append_all_csv`` is False, flush route rows after
        every N **fields** processed (first PostGIS write uses ``replace``, then ``append``).
        Nearest table uses the same pattern when ``write_nearest_csv`` is True.
        Use ``0`` or ``None`` for a single load at the end only. Default ``100``.
    field_id_modulus, field_id_remainder :
        If set, keep only parcels where ``field_id % modulus == remainder`` (chunked runs).
    append_all_csv :
        If True, append to ``output_all_routes_path`` without header when the file already exists.
    write_nearest_csv :
        If False, skip writing the per-field nearest summary (use after merging all-route chunks).
    field_workers :
        Number of parallel processes for per-field routing on **Linux** (``fork``). Each field still
        runs one Dijkstra tree then all facility targets. Ignored on other platforms (sequential).
        Use ``1`` to disable parallelism.
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

    # Download graph for the extent of **fields** plus enough margin to cover snapping,
    # rural connectors, and any facility within ``max_candidate_miles`` (great-circle) of a field.
    # Do not union facility geometries into the base bbox: a statewide elevator list makes the
    # Overpass query enormous even when parcels are local.
    f_bounds = fields.geometry.total_bounds
    bf = (float(f_bounds[0]), float(f_bounds[1]), float(f_bounds[2]), float(f_bounds[3]))
    buffer_miles = max(
        float(network_bbox_buffer_miles),
        float(max_candidate_miles) + 3.0,
        5.0,
    )
    bbox = expand_bounds_miles(*bf, buffer_miles=buffer_miles)
    logger.info("Loading OSM drive network for bbox %s", bbox)
    G = load_drive_graph(bbox, nx_osm_path=Path(osm_graph_path) if osm_graph_path else None)
    G = assign_travel_times(G, speeds_mph)
    logger.info("Projected graph: %d nodes, %d edges", len(G), G.number_of_edges())

    fac_nodes = nearest_graph_nodes_batch(G, flon, flat)
    n_snap = sum(1 for x in fac_nodes if x is not None)
    logger.info("Snapped %d / %d facilities to drive network nodes", n_snap, len(facilities))

    all_rows: List[Dict[str, Any]] = []

    pg_every = postgis_commit_every_n_fields
    if pg_every is not None and pg_every < 0:
        raise ValueError("postgis_commit_every_n_fields must be >= 0 (use 0 or None for one-shot PostGIS load)")
    if pg_every == 0:
        pg_every = None
    postgis_batch = bool(postgis_url and not append_all_csv and pg_every is not None)
    pending_pg: List[Dict[str, Any]] = []
    fields_since_pg = 0
    pg_all_first = True
    pg_nn_first = True

    def flush_postgis_batch(force: bool = False) -> None:
        nonlocal pending_pg, fields_since_pg, pg_all_first, pg_nn_first
        if not postgis_batch or not pending_pg:
            return
        if not force and fields_since_pg < (pg_every or 0):
            return
        assert postgis_url is not None
        df_b = pd.DataFrame(pending_pg)
        mode_a = "replace" if pg_all_first else "append"
        write_postgis(df_b, postgis_url, postgis_all_table, if_exists=mode_a)
        logger.info(
            "PostGIS batch %s: %d route rows -> %s",
            mode_a,
            len(df_b),
            postgis_all_table,
        )
        pg_all_first = False
        if write_nearest_csv:
            df_nb = build_nearest_from_routes_all(df_b)
            mode_n = "replace" if pg_nn_first else "append"
            write_postgis(df_nb, postgis_url, postgis_nearest_table, if_exists=mode_n)
            logger.info(
                "PostGIS batch %s: %d nearest rows -> %s",
                mode_n,
                len(df_nb),
                postgis_nearest_table,
            )
            pg_nn_first = False
        pending_pg.clear()
        fields_since_pg = 0

    worker_ctx: Dict[str, Any] = {
        "G": G,
        "fields": fields,
        "fid_col": fid_col,
        "owner_col_resolved": owner_col_resolved,
        "flon": flon,
        "flat": flat,
        "fac_ids": fac_ids,
        "fac_names": fac_names,
        "fac_nodes": fac_nodes,
        "max_candidate_miles": max_candidate_miles,
        "unload_val": unload_val,
    }

    fw = max(1, int(field_workers))
    use_mp = fw > 1 and sys.platform == "linux" and len(fields) > 0
    if fw > 1 and sys.platform != "linux":
        logger.warning(
            "field_workers=%d ignored on %s (parallel routing uses Linux fork); using one worker",
            fw,
            sys.platform,
        )
        use_mp = False

    if use_mp:
        logger.info("Routing fields with %d parallel workers (process pool)", fw)
        global _FIELD_WORKER_CTX
        _FIELD_WORKER_CTX = worker_ctx
        try:
            mp_ctx = multiprocessing.get_context("fork")
            cs = max(1, len(fields) // (fw * 4))
            with mp_ctx.Pool(fw) as pool:
                for batch in tqdm(
                    pool.imap(_field_worker_entry, range(len(fields)), chunksize=cs),
                    total=len(fields),
                    desc="Fields",
                ):
                    mark = len(all_rows)
                    try:
                        all_rows.extend(batch)
                    finally:
                        pending_pg.extend(all_rows[mark:])
                        fields_since_pg += 1
                        flush_postgis_batch(force=False)
        finally:
            _FIELD_WORKER_CTX = None
    else:
        for idx in tqdm(range(len(fields)), desc="Fields"):
            mark = len(all_rows)
            try:
                all_rows.extend(_build_routes_for_field_index(idx, worker_ctx))
            finally:
                pending_pg.extend(all_rows[mark:])
                fields_since_pg += 1
                flush_postgis_batch(force=False)

    if postgis_batch:
        flush_postgis_batch(force=True)

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
        if not postgis_batch:
            write_postgis(df_all, postgis_url, postgis_all_table, if_exists="replace")
            if write_nearest_csv:
                write_postgis(df_nearest, postgis_url, postgis_nearest_table, if_exists="replace")
        else:
            logger.info(
                "PostGIS loaded in batches of %d fields; tables are up to date (no final bulk write).",
                pg_every,
            )
    elif postgis_url and append_all_csv:
        logger.warning(
            "PostGIS load skipped (append_all_csv=True). Merge CSV chunks, then merge_nearest + load once."
        )

    return df_all, df_nearest
