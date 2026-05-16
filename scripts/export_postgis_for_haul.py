#!/usr/bin/env python3
"""Export parcels and grain elevators from AgInfo PostGIS for haul_routing CLI."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine, text

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ',.\-/]*$")


def _safe_token(label: str, name: str) -> str:
    s = label.strip()
    if not s or _SAFE_TOKEN.fullmatch(s) is None:
        raise SystemExit(
            f"Invalid {name} {label!r} (allowed: letters, digits, space, comma, - . / ')"
        )
    return s


def _sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="haul_routing/runs/parcels_30mi",
        help="Directory for parcels_fields.gpkg and facilities gpkg",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("HAUL_PG_URL", ""),
        help="SQLAlchemy URL (default env HAUL_PG_URL)",
    )
    parser.add_argument(
        "--all-facility-types",
        action="store_true",
        help="Export all ACTIVE facilities with geometry (default: grain elevators only)",
    )
    parser.add_argument(
        "--agricultural-only",
        action="store_true",
        help="Parcels: keep rows where usedesc ILIKE 'Agricultural%%' (matches 'Agricultural Use', etc.)",
    )
    parser.add_argument(
        "--skip-homesite",
        action="store_true",
        help="Exclude parcels with usedesc case-insensitively equal to 'Farm Homesite'",
    )
    parser.add_argument(
        "--exclude-usedesc",
        action="append",
        default=None,
        metavar="TEXT",
        help="Exclude parcels with this usedesc (trimmed, case-insensitive). Repeatable.",
    )
    parser.add_argument(
        "--min-gisacre",
        type=float,
        default=None,
        help=(
            "Minimum parcel acres: GREATEST(COALESCE(gisacre,0), COALESCE(ll_gisacre,0)) must "
            "meet this threshold (NULL columns treated as 0)"
        ),
    )
    parser.add_argument(
        "--counties",
        default=None,
        help="Comma-separated county names (matched case-insensitively to parcels.county after trim)",
    )
    parser.add_argument(
        "--include-usedesc-gisacre",
        action="store_true",
        help="Add usedesc and gisacre columns to the parcels GeoPackage for QA",
    )
    parser.add_argument(
        "--limit-parcels",
        type=int,
        default=None,
        metavar="N",
        help="Export at most N parcels after filters, stable order by id (for test / sample runs)",
    )
    parser.add_argument(
        "--parcel-bbox",
        default=None,
        metavar="W,S,E,N",
        help=(
            "west,south,east,north decimal degrees (WGS84). Keep parcels whose geom intersects "
            "this envelope. Strongly recommended with --limit-parcels so OSM download stays local."
        ),
    )
    args = parser.parse_args()

    db_url = args.database_url.strip()
    if not db_url:
        raise SystemExit(
            "Set HAUL_PG_URL, e.g. postgresql://agadmin:pass@aginfo-postgis:5432/aginfo"
        )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    engine = create_engine(db_url)

    clauses: list[str] = ["geom IS NOT NULL"]
    params: dict[str, float] = {}

    if args.agricultural_only:
        clauses.append("usedesc ILIKE 'Agricultural%'")

    excludes_norm: list[str] = []
    for ex in list(args.exclude_usedesc or []):
        excludes_norm.append(_safe_token(ex, "exclude-usedesc").lower())
    if args.skip_homesite:
        excludes_norm.append("farm homesite")
    excludes_norm = list(dict.fromkeys(excludes_norm))
    if excludes_norm:
        in_list = ", ".join(_sql_quote(x) for x in excludes_norm)
        clauses.append(
            f"lower(trim(coalesce(usedesc, ''))) NOT IN ({in_list})"
        )

    if args.min_gisacre is not None:
        clauses.append(
            "GREATEST(COALESCE(gisacre, 0::numeric), COALESCE(ll_gisacre, 0::numeric)) >= :min_ac"
        )
        params["min_ac"] = float(args.min_gisacre)

    if args.counties:
        parts = [p.strip() for p in args.counties.split(",") if p.strip()]
        if not parts:
            raise SystemExit("--counties was empty after parsing")
        lows = []
        for p in parts:
            lows.append(_safe_token(p, "county").lower())
        in_list = ", ".join(_sql_quote(c) for c in lows)
        clauses.append(f"lower(trim(county)) IN ({in_list})")

    if args.parcel_bbox:
        raw_parts = [p.strip() for p in args.parcel_bbox.split(",")]
        if len(raw_parts) != 4:
            raise SystemExit(
                "--parcel-bbox must be west,south,east,north in WGS84 (decimal degrees)"
            )
        try:
            w, s, e, n = (float(raw_parts[0]), float(raw_parts[1]), float(raw_parts[2]), float(raw_parts[3]))
        except ValueError as exc:
            raise SystemExit(f"--parcel-bbox values must be numeric: {exc}") from exc
        if w >= e or s >= n:
            raise SystemExit("--parcel-bbox requires west < east and south < north")
        if not (-180.0 <= w <= 180.0 and -180.0 <= e <= 180.0 and -90.0 <= s <= 90.0 and -90.0 <= n <= 90.0):
            raise SystemExit("--parcel-bbox outside valid WGS84 ranges")
        clauses.append("geom && ST_MakeEnvelope(:pb_w, :pb_s, :pb_e, :pb_n, 4326)")
        params["pb_w"] = w
        params["pb_s"] = s
        params["pb_e"] = e
        params["pb_n"] = n

    extra_cols = ""
    if args.include_usedesc_gisacre:
        extra_cols = ", usedesc, gisacre"

    read_params: dict = dict(params)
    order_limit = ""
    if args.limit_parcels is not None:
        n = int(args.limit_parcels)
        if n < 1:
            raise SystemExit("--limit-parcels must be >= 1")
        read_params["parcel_limit"] = n
        order_limit = " ORDER BY id ASC LIMIT :parcel_limit"

    parcels_sql = text(
        f"""
        SELECT id AS field_id, owner AS owner_name, county{extra_cols}, geom
        FROM parcels
        WHERE {" AND ".join(clauses)}
        {order_limit}
        """
    )

    read_args: dict = {"geom_col": "geom"}
    if read_params:
        read_args["params"] = read_params
    fields = gpd.read_postgis(parcels_sql, engine, **read_args)
    if fields.crs is None:
        fields = fields.set_crs(4326)
    if fields.empty:
        raise SystemExit(
            "0 parcels matched your filters (bbox, counties, min_gisacre, etc.). "
            "Widen --parcel-bbox, set --counties, or relax filters."
        )
    p_parcel = out / "parcels_fields.gpkg"
    fields.to_file(p_parcel, driver="GPKG", layer="parcels")
    print(f"Wrote {len(fields)} parcels -> {p_parcel}")

    if args.all_facility_types:
        fac_sql = """
            SELECT facility_id, name AS facility_name, geom
            FROM facility
            WHERE status = 'ACTIVE' AND geom IS NOT NULL
            """
        fac_path = out / "facilities_all.gpkg"
    else:
        # Limit candidate elevators to the Great Plains corridor around loaded parcels
        # (excludes national HQs with bad geocodes that blow up OSM bbox, e.g. VA/FL/MA).
        fac_sql = """
            SELECT facility_id, name AS facility_name, geom
            FROM facility
            WHERE status = 'ACTIVE'
              AND geom IS NOT NULL
              AND facility_type_id = 1
              AND geom::geometry && ST_MakeEnvelope(-103.5, 36.0, -94.0, 40.5, 4326)
            """
        fac_path = out / "facilities_elevators.gpkg"

    facilities = gpd.read_postgis(fac_sql, engine, geom_col="geom")
    if facilities.crs is None:
        facilities = facilities.set_crs(4326)
    facilities.to_file(fac_path, driver="GPKG", layer="facilities")
    print(f"Wrote {len(facilities)} facilities -> {fac_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
