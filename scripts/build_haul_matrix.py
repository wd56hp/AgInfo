#!/usr/bin/env python3
"""CLI for OSM-based field-to-facility haul routing matrix."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Repo root: parent of scripts/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from haul_routing.pipeline import calculate_field_to_facility_routes

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute drive miles and times from field centroids to grain facilities via OSM."
    )
    parser.add_argument("--fields", required=True, help="Path to fields GeoPackage / Shapefile / GeoJSON")
    parser.add_argument("--facilities", required=True, help="Path to facilities vector file")
    parser.add_argument("--all-output", required=True, help="Output CSV for all field–facility pairs routed")
    parser.add_argument(
        "--nearest-output",
        default=None,
        help="Output CSV: closest facility per field (omit with --no-nearest when chunking)",
    )
    parser.add_argument("--max-miles", type=float, default=50.0, help="Great-circle prefilter for facilities (miles)")
    parser.add_argument("--unload-minutes", type=float, default=None, help="Unload time (default from YAML)")
    parser.add_argument(
        "--speed-config",
        default=None,
        help="YAML speed table (default: aginfo/config/road_speeds.yaml or package default)",
    )
    parser.add_argument(
        "--network-buffer-miles",
        type=float,
        default=10.0,
        help="Extra padding beyond data extent when downloading OSM",
    )
    parser.add_argument("--osm-graph", default=None, help="Optional local GraphML or OSM XML from OSMnx")
    parser.add_argument("--fields-layer", default=None, help="GeoPackage layer name for fields")
    parser.add_argument("--facilities-layer", default=None, help="GeoPackage layer name for facilities")
    parser.add_argument("--field-id-column", default="field_id", help="Field identifier column")
    parser.add_argument("--owner-column", default="owner_name", help="Owner / operator column (0 to skip)")
    parser.add_argument("--facility-id-column", default="facility_id", help="Facility id column")
    parser.add_argument("--facility-name-column", default="facility_name", help="Facility name column")
    parser.add_argument("--all-gpkg", default=None, help="Optional GeoPackage output (all routes)")
    parser.add_argument("--nearest-gpkg", default=None, help="Optional GeoPackage output (nearest only)")
    parser.add_argument(
        "--postgis-url",
        default=None,
        help="SQLAlchemy URL, e.g. postgresql://agadmin:pass@localhost:15433/aginfo",
    )
    parser.add_argument("--postgis-all-table", default="haul_field_facility_routes_all")
    parser.add_argument("--postgis-nearest-table", default="haul_field_facility_routes_nearest")
    parser.add_argument(
        "--postgis-commit-every",
        type=int,
        default=100,
        help="With --postgis-url: write to DB after every N fields (route rows). Use 0 for a single load at the end only.",
    )
    parser.add_argument(
        "--field-modulus",
        type=int,
        default=None,
        help="Chunk: keep parcels where field_id %% modulus == remainder (see --field-remainder)",
    )
    parser.add_argument(
        "--field-remainder",
        type=int,
        default=None,
        help="Chunk: remainder for --field-modulus (required when modulus is set)",
    )
    parser.add_argument(
        "--append-all-csv",
        action="store_true",
        help=(
            "Append rows to --all-output without CSV header when the file already exists; "
            "skips PostGIS load and full GPKG writes (merge chunks, then merge_nearest, then load once)."
        ),
    )
    parser.add_argument(
        "--no-nearest",
        action="store_true",
        help="Do not write nearest CSV; run scripts/merge_haul_nearest.py after concatenating chunks",
    )
    parser.add_argument(
        "--field-workers",
        type=int,
        default=4,
        help=(
            "Parallel processes for per-field routing on Linux (fork). "
            "Each field runs one Dijkstra to all candidate facilities. Use 1 to disable. "
            "Ignored on non-Linux (sequential)."
        ),
    )
    args = parser.parse_args()

    if args.field_workers < 1:
        parser.error("--field-workers must be >= 1")

    write_nearest = not args.no_nearest
    if write_nearest and not args.nearest_output:
        parser.error("--nearest-output is required unless --no-nearest")
    if args.field_modulus is not None and args.field_remainder is None:
        parser.error("--field-remainder is required when --field-modulus is set")
    if args.field_modulus is None and args.field_remainder is not None:
        parser.error("--field-modulus is required when --field-remainder is set")

    calculate_field_to_facility_routes(
        fields_path=args.fields,
        facilities_path=args.facilities,
        output_all_routes_path=args.all_output,
        output_nearest_path=args.nearest_output,
        field_id_modulus=args.field_modulus,
        field_id_remainder=args.field_remainder,
        append_all_csv=args.append_all_csv,
        write_nearest_csv=write_nearest,
        max_candidate_miles=args.max_miles,
        unload_minutes=args.unload_minutes,
        speed_config_path=args.speed_config,
        network_bbox_buffer_miles=args.network_buffer_miles,
        osm_graph_path=args.osm_graph,
        fields_layer=args.fields_layer,
        facilities_layer=args.facilities_layer,
        field_id_column=args.field_id_column,
        owner_column=owner_col,
        facility_id_column=args.facility_id_column,
        facility_name_column=args.facility_name_column,
        postgis_url=args.postgis_url,
        postgis_all_table=args.postgis_all_table,
        postgis_nearest_table=args.postgis_nearest_table,
        postgis_commit_every_n_fields=args.postgis_commit_every,
        field_workers=args.field_workers,
        output_all_gpkg=args.all_gpkg,
        output_nearest_gpkg=args.nearest_gpkg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
