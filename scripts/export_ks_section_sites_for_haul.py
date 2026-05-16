#!/usr/bin/env python3
"""Write ks_plss_section_site from PostGIS to a GeoPackage for build_haul_matrix.py (field_id = feature_id)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _pg_url_from_env() -> str:
    u = os.environ.get("HAUL_PG_URL", "").strip()
    if u:
        return u
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--postgis-url", default=os.environ.get("HAUL_PG_URL", ""))
    p.add_argument("--out", type=Path, required=True, help="Output .gpkg path")
    p.add_argument(
        "--layer",
        default="section_sites",
        help="Layer name inside the GeoPackage (default section_sites)",
    )
    args = p.parse_args()

    url = args.postgis_url.strip() or _pg_url_from_env()
    if not url:
        raise SystemExit("Set --postgis-url or HAUL_PG_URL or .env POSTGRES_*")

    eng = create_engine(url)
    with eng.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM ks_plss_section_site")).scalar()
    if not n:
        raise SystemExit(
            "ks_plss_section_site is empty — load section centroids first "
            "(scripts/build_ks_section_elevator_map.py load-sites)."
        )

    gdf = gpd.read_postgis(
        "SELECT feature_id AS field_id, geom FROM ks_plss_section_site",
        eng,
        geom_col="geom",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    gdf.to_file(args.out, layer=args.layer, driver="GPKG")
    print(f"Wrote {n} points to {args.out} layer={args.layer} (column field_id for --field-id-column).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
