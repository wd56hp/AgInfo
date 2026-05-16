#!/usr/bin/env python3
"""Load merged routes_all.csv + routes_nearest.csv into PostGIS (after chunked haul runs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from haul_routing.db_export import write_postgis  # noqa: E402


def _drop_qgis_views_if_exist(engine_url: str) -> None:
    """GeoPandas ``replace`` issues DROP TABLE; dependent views must be removed first."""
    eng = create_engine(engine_url)
    with eng.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS v_haul_routes_all_qgis CASCADE"))
        conn.execute(text("DROP VIEW IF EXISTS v_haul_routes_nearest_qgis CASCADE"))


def _drop_ks_section_haul_views_if_exist(engine_url: str) -> None:
    """KS section views reference haul_ks_section_* tables; drop before ``to_postgis(..., replace)``."""
    eng = create_engine(engine_url)
    with eng.begin() as conn:
        for name in (
            "v_ks_section_nearest_facility",
            "v_ks_section_facility_haul_ranked",
            "v_ks_section_facility_fastest_route",
            "v_ks_section_facility_haul_all",
        ):
            conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))


def _apply_qgis_views_sql(repo_root: Path, engine_url: str) -> None:
    path = repo_root / "haul_routing" / "sql" / "qgis_views.sql"
    if not path.is_file():
        return
    eng = create_engine(engine_url)
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
    blob = "\n".join(lines)
    stmts = [s.strip() for s in blob.split(";") if s.strip()]
    with eng.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt + ";"))


def main() -> int:
    p = argparse.ArgumentParser(description="Replace haul PostGIS tables from CSV outputs.")
    p.add_argument("--all-csv", required=True)
    p.add_argument("--nearest-csv", required=True)
    p.add_argument(
        "--postgis-url",
        default=os.environ.get("HAUL_PG_URL", ""),
        help="SQLAlchemy URL (default env HAUL_PG_URL)",
    )
    p.add_argument("--all-table", default="haul_field_facility_routes_all")
    p.add_argument("--nearest-table", default="haul_field_facility_routes_nearest")
    p.add_argument(
        "--no-qgis-views",
        action="store_true",
        help="Do not drop/recreate v_haul_routes_*_qgis (use when loading non-parcel haul tables)",
    )
    args = p.parse_args()

    url = args.postgis_url.strip()
    if not url:
        raise SystemExit("Set --postgis-url or HAUL_PG_URL")

    import pandas as pd

    df_all = pd.read_csv(args.all_csv)
    df_nn = pd.read_csv(args.nearest_csv)
    if not args.no_qgis_views:
        _drop_qgis_views_if_exist(url)
    if args.all_table == "haul_ks_section_facility_routes_all":
        _drop_ks_section_haul_views_if_exist(url)
    write_postgis(df_all, url, args.all_table, if_exists="replace")
    write_postgis(df_nn, url, args.nearest_table, if_exists="replace")
    if not args.no_qgis_views:
        _apply_qgis_views_sql(_ROOT, url)
    print(f"Loaded {len(df_all)} rows -> {args.all_table}, {len(df_nn)} -> {args.nearest_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
