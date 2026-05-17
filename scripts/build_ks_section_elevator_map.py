#!/usr/bin/env python3
"""Kansas PLSS section → nearest grain elevator map (standalone from parcels / haul_routing).

The exported PLSS CSVs in ks_plss_* do not include geometry. You must supply a vector layer
(section polygons or centroids) that carries a PLSS key column matching ``ks_plss_section``
(typically ``section_range_township`` like ``S22-T4S-R37W`` or ``plss_key`` like ``S22 T4S R37W``).

Workflow::

  1. python scripts/build_ks_section_elevator_map.py apply-schema
  2. python scripts/build_ks_section_elevator_map.py load-sites --vector /path/to/sections.gpkg --layer ...
  3. python scripts/build_ks_section_elevator_map.py compute
  4. python scripts/build_ks_section_elevator_map.py export --out /path/to/ks_section_elevators.gpkg

Distances are great-circle miles (PostGIS geography ``ST_Distance``), comparable to
``facility_parcels_8mi`` style queries — not drive distance.

Environment / URL: same as other loaders — ``HAUL_PG_URL`` or ``POSTGRES_*`` or ``.env`` (see ``--help``).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_ROOT = Path(__file__).resolve().parents[1]
_INIT_SQL = _ROOT / "db" / "init" / "14_schema_ks_section_elevator.sql"


def _pg_url_from_env() -> str:
    u = os.environ.get("HAUL_PG_URL", "").strip()
    if u:
        return u
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    db = os.environ.get("POSTGRES_DB", "").strip()
    if user and password and db:
        host = os.environ.get("POSTGRES_HOST", "localhost").strip()
        port = os.environ.get("POSTGRES_PORT", os.environ.get("POSTGIS_HOST_PORT", "5432")).strip()
        from urllib.parse import quote_plus

        return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"

    env_path = _ROOT / ".env"
    if not env_path.is_file():
        return ""
    vals: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v0 = line.partition("=")
        k, v = k.strip(), v0.strip().strip("'").strip('"')
        if k:
            vals[k] = v
    user = vals.get("POSTGRES_USER", "agadmin")
    password = vals.get("POSTGRES_PASSWORD", "")
    db = vals.get("POSTGRES_DB", "aginfo")
    if not password:
        return ""
    host = vals.get("POSTGRES_HOST", "localhost")
    port = vals.get("POSTGRES_PORT", vals.get("POSTGIS_HOST_PORT", "5432"))
    from urllib.parse import quote_plus

    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def _apply_sql_file(engine: Engine, path: Path) -> None:
    raw_text = path.read_text(encoding="utf-8")
    stripped = "\n".join(ln for ln in raw_text.splitlines() if not ln.strip().startswith("--"))
    stmts: list[str] = []
    buf: list[str] = []
    for line in stripped.splitlines():
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                stmts.append(stmt.rstrip(";"))
            buf = []
    if buf:
        stmt = "\n".join(buf).strip()
        if stmt:
            stmts.append(stmt.rstrip(";"))
    with engine.begin() as conn:
        for stmt in stmts:
            if not stmt.strip():
                continue
            conn.execute(text(stmt + ";"))


def _engine_from_args(ns: argparse.Namespace) -> Engine:
    url = (getattr(ns, "postgis_url", "") or _pg_url_from_env()).strip()
    if not url:
        raise SystemExit("Set --postgis-url or HAUL_PG_URL or populate .env POSTGRES_*")
    return create_engine(url)


def _norm_join_key(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"[\s\-_]+", "", str(value).strip().upper())


def _build_section_lookup(engine: Engine) -> tuple[dict[str, int], int]:
    q = text(
        """
        SELECT s.feature_id, s.section_range_township, k.plss_key
        FROM ks_plss_section s
        LEFT JOIN v_ks_plss_section_key k ON k.feature_id = s.feature_id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(q).mappings().all()
    lookup: dict[str, int] = {}
    for r in rows:
        fid = r["feature_id"]
        for raw in (r["section_range_township"], r["plss_key"]):
            if raw is None:
                continue
            key = str(raw).strip()
            if key:
                lookup.setdefault(key, fid)
                nk = _norm_join_key(key)
                if nk:
                    lookup.setdefault(nk, fid)
    return lookup, len(rows)


def cmd_apply_schema(ns: argparse.Namespace) -> None:
    if not _INIT_SQL.is_file():
        raise SystemExit(f"Missing {_INIT_SQL}")
    eng = _engine_from_args(ns)
    _apply_sql_file(eng, _INIT_SQL)
    print(f"Applied {_INIT_SQL.name}")


def cmd_load_sites(ns: argparse.Namespace) -> None:
    vf = Path(ns.vector)
    if not vf.is_file():
        raise SystemExit(f"Missing vector file {vf}")
    eng = _engine_from_args(ns)
    lookup, nsec = _build_section_lookup(eng)
    if nsec == 0:
        print("Warning: ks_plss_section is empty — join keys will not match until PLSS is loaded.", file=sys.stderr)

    gdf = gpd.read_file(vf, layer=ns.layer) if ns.layer else gpd.read_file(vf)
    if ns.join_column not in gdf.columns:
        raise SystemExit(f"Column {ns.join_column!r} not found; have {list(gdf.columns)}")
    if gdf.crs is None:
        raise SystemExit("Vector layer has no CRS; set CRS before loading.")
    wgs = gdf.to_crs(4326)
    centroids = wgs.geometry.centroid
    wgs = gpd.GeoDataFrame(wgs.drop(columns="geometry"), geometry=centroids, crs="EPSG:4326")

    records: list[dict] = []
    unmatched = 0
    for _, row in wgs.iterrows():
        jval = row[ns.join_column]
        if jval is None or (isinstance(jval, float) and pd.isna(jval)):
            unmatched += 1
            continue
        sval = str(jval).strip()
        fid = lookup.get(sval) or lookup.get(_norm_join_key(sval))
        if fid is None:
            unmatched += 1
            continue
        records.append(
            {
                "feature_id": int(fid),
                "source_note": ns.source_note or vf.name,
                "geometry": row.geometry,
            }
        )

    if not records:
        raise SystemExit("No rows matched ks_plss_section — check --join-column and PLSS keys.")

    out = gpd.GeoDataFrame(records, crs="EPSG:4326")
    out = out.rename(columns={"geometry": "geom"}).set_geometry("geom")
    dupes = out["feature_id"].duplicated().sum()
    if dupes:
        out = out.drop_duplicates(subset="feature_id", keep="first")
        print(f"Dropped {dupes} duplicate feature_ids (kept first centroid).", file=sys.stderr)

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM ks_plss_section_site"))
    out.to_postgis(
        "ks_plss_section_site",
        eng,
        if_exists="append",
        index=False,
        geom_col="geom",
    )
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ks_plss_section_site s
                SET plss_key = k.plss_key,
                    section_range_township = k.section_range_township
                FROM v_ks_plss_section_key k
                WHERE k.feature_id = s.feature_id
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE ks_plss_section_site s
                SET section_range_township = COALESCE(s.section_range_township, sec.section_range_township),
                    plss_key = COALESCE(s.plss_key, sec.section_range_township)
                FROM ks_plss_section sec
                WHERE sec.feature_id = s.feature_id
                """
            )
        )

    print(
        f"Inserted {len(out)} section site rows into ks_plss_section_site "
        f"({unmatched} source rows did not match)."
    )


def cmd_compute(ns: argparse.Namespace) -> None:
    eng = _engine_from_args(ns)
    state_filter = ""
    params: dict = {"ftype": ns.facility_type_id}
    if ns.ks_facilities_only:
        state_filter = "AND BTRIM(COALESCE(f.state::text, '')) = 'KS'"
    sql_ins = f"""
    INSERT INTO ks_section_nearest_grain_elevator (
        feature_id,
        plss_key,
        section_range_township,
        section_geom,
        nearest_facility_id,
        nearest_facility_name,
        company_id,
        facility_geom,
        distance_miles,
        connector_line,
        facility_type_id,
        computed_at
    )
    SELECT
        s.feature_id,
        COALESCE(k.plss_key, sec.section_range_township),
        COALESCE(k.section_range_township, sec.section_range_township),
        s.geom,
        nf.facility_id,
        nf.name,
        nf.company_id,
        nf.geom,
        ST_Distance(s.geom::geography, nf.geom::geography) / 1609.344::double precision,
        ST_MakeLine(s.geom, nf.geom),
        nf.facility_type_id,
        now()
    FROM ks_plss_section_site s
    LEFT JOIN v_ks_plss_section_key k ON k.feature_id = s.feature_id
    LEFT JOIN ks_plss_section sec ON sec.feature_id = s.feature_id
    CROSS JOIN LATERAL (
        SELECT f.facility_id, f.name, f.company_id, f.geom, f.facility_type_id
        FROM facility f
        WHERE f.facility_type_id = :ftype
          AND f.geom IS NOT NULL
          AND COALESCE(f.status, 'ACTIVE') = 'ACTIVE'
          {state_filter}
        ORDER BY s.geom <-> f.geom
        LIMIT 1
    ) nf
    """
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE ks_section_nearest_grain_elevator"))
        conn.execute(text(sql_ins), params)
    with eng.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM ks_section_nearest_grain_elevator")).scalar()
    print(f"ks_section_nearest_grain_elevator populated with {n} rows.")


def cmd_export(ns: argparse.Namespace) -> None:
    eng = _engine_from_args(ns)
    out = Path(ns.out)
    pts = gpd.read_postgis(
        """
        SELECT feature_id, plss_key, section_range_township, nearest_facility_id,
               nearest_facility_name, company_id, distance_miles, computed_at,
               section_geom AS geom
        FROM ks_section_nearest_grain_elevator
        """,
        eng,
        geom_col="geom",
    )
    lines = gpd.read_postgis(
        """
        SELECT feature_id, plss_key, nearest_facility_id, nearest_facility_name,
               distance_miles, connector_line AS geom
        FROM ks_section_nearest_grain_elevator
        WHERE connector_line IS NOT NULL
        """,
        eng,
        geom_col="geom",
    )
    if pts.empty:
        raise SystemExit("ks_section_nearest_grain_elevator is empty — run compute first.")
    if out.exists():
        out.unlink()
    pts.to_file(out, layer="section_nearest_elevator", driver="GPKG")
    if not lines.empty:
        lines.to_file(out, layer="section_to_elevator_line", driver="GPKG", mode="a")
    print(f"Wrote {out} (layers: section_nearest_elevator, section_to_elevator_line if non-empty).")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--postgis-url", default=os.environ.get("HAUL_PG_URL", ""))

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("apply-schema", help="Create tables, indexes, and QGIS-oriented views on nearest-elevator output.")

    p_load = sub.add_parser("load-sites", help="Load section centroid points from a vector file into ks_plss_section_site.")
    p_load.add_argument("--vector", required=True, type=Path, help="Path to GeoPackage, GeoJSON, shapefile, …")
    p_load.add_argument("--layer", default=None, help="Layer name (GeoPackage / multi-layer sources)")
    p_load.add_argument(
        "--join-column",
        default="section_range_township",
        help="Attribute column matching ks_plss_section.section_range_township or v_ks_plss_section_key.plss_key",
    )
    p_load.add_argument("--source-note", default="", help="Optional note stored on each loaded row")

    p_cmp = sub.add_parser("compute", help="Fill ks_section_nearest_grain_elevator from ks_plss_section_site + facility.")
    p_cmp.add_argument("--facility-type-id", type=int, default=1, dest="facility_type_id", help="Default: 1 = Grain Elevator")
    p_cmp.add_argument(
        "--ks-facilities-only",
        action="store_true",
        help="Only consider facilities with state KS (exclude border out-of-state elevators).",
    )

    p_exp = sub.add_parser("export", help="Write GeoPackage map layers from ks_section_nearest_grain_elevator.")
    p_exp.add_argument("--out", required=True, type=Path, help="Output .gpkg path")

    ns = p.parse_args()
    if ns.command == "apply-schema":
        cmd_apply_schema(ns)
    elif ns.command == "load-sites":
        cmd_load_sites(ns)
    elif ns.command == "compute":
        cmd_compute(ns)
    elif ns.command == "export":
        cmd_export(ns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
