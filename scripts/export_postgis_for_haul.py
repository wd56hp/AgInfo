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
        help="Minimum parcel gisacre (NULL gisacre treated as 0)",
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
        clauses.append("COALESCE(gisacre, 0) >= :min_ac")
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

    extra_cols = ""
    if args.include_usedesc_gisacre:
        extra_cols = ", usedesc, gisacre"

    parcels_sql = text(
        f"""
        SELECT id AS field_id, owner AS owner_name, county{extra_cols}, geom
        FROM parcels
        WHERE {" AND ".join(clauses)}
        """
    )

    read_args: dict = {"geom_col": "geom"}
    if params:
        read_args["params"] = params
    fields = gpd.read_postgis(parcels_sql, engine, **read_args)
    if fields.crs is None:
        fields = fields.set_crs(4326)
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
