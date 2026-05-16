#!/usr/bin/env python3
"""Fill ks_plss_section_site from Kansas DASC statewide PLSS section polygons (ArcGIS FeatureServer).

Source layer matches your ``ks_plss_section`` CSV lineage (``Kansas_PLSS_View``): 82,896 sections.
Join is on ``PLSS_NAD83`` (service) = ``plss_nad83_id`` (``ks_plss_section``).

Requires: ``ks_plss_section`` already loaded. Replaces **all** rows in ``ks_plss_section_site`` (TRUNCATE).

PostGIS URL: ``--postgis-url`` or ``HAUL_PG_URL`` / ``POSTGRES_*`` / ``.env`` (same pattern as other loaders).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_ROOT = Path(__file__).resolve().parents[1]

FEATURE_QUERY_BASE = (
    "https://services1.arcgis.com/q2CglofYX6ACNEeu/arcgis/rest/services/"
    "Kansas_PLSS_View/FeatureServer/0/query"
)


def _pg_url_from_args(ns: argparse.Namespace) -> str:
    u = (getattr(ns, "postgis_url", None) or os.environ.get("HAUL_PG_URL", "")).strip()
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


def _fetch_geojson_page(offset: int, page_size: int, retries: int) -> dict:
    params = {
        "where": "1=1",
        "outFields": "S_R_T,PLSS_NAD83,FID",
        "outSR": "4326",
        "returnGeometry": "true",
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
        "f": "geojson",
    }
    url = f"{FEATURE_QUERY_BASE}?{urllib.parse.urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgInfo-ks-plss-loader/1.0"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(min(60, 2**attempt))
    raise RuntimeError(f"ArcGIS query failed after retries: {last_err}") from last_err


def _enrich_site_table(engine: Engine) -> None:
    with engine.begin() as conn:
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--postgis-url", default=os.environ.get("HAUL_PG_URL", ""))
    p.add_argument("--page-size", type=int, default=1000, help="ArcGIS page size (service often caps at 1000)")
    p.add_argument("--retries", type=int, default=4)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and join only; print counts, do not write PostGIS",
    )
    p.add_argument(
        "--max-batches",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N ArcGIS pages (smoke test)",
    )
    ns = p.parse_args()

    url = _pg_url_from_args(ns).strip()
    if not url:
        raise SystemExit("Set --postgis-url or HAUL_PG_URL / .env POSTGRES_*")

    eng = create_engine(url)
    df_lut = pd.read_sql_query("SELECT feature_id, plss_nad83_id FROM ks_plss_section", eng)
    if df_lut.empty:
        raise SystemExit("ks_plss_section is empty — load PLSS CSVs first.")
    lookup: dict[int, int] = {}
    for _, row in df_lut.iterrows():
        nid = int(row["plss_nad83_id"])
        lookup[nid] = int(row["feature_id"])

    fc0 = _fetch_geojson_page(0, 1, ns.retries)
    props_ex = (fc0.get("features") or [{}])[0].get("properties") or {}
    if "PLSS_NAD83" not in props_ex and "plss_nad83" not in str(props_ex).lower():
        print("Warning: response properties sample:", list(props_ex.keys()), file=sys.stderr)

    unmatched = 0
    bad_geom = 0
    offset = 0
    total_written = 0
    batch_i = 0

    if not ns.dry_run:
        with eng.begin() as conn:
            conn.execute(text("TRUNCATE ks_plss_section_site"))

    while True:
        fc = _fetch_geojson_page(offset, ns.page_size, ns.retries)
        feats = fc.get("features") or []
        if not feats:
            break
        records: list[dict] = []
        for feat in feats:
            props = feat.get("properties") or {}
            nad = props.get("PLSS_NAD83")
            if nad is None:
                unmatched += 1
                continue
            try:
                nid = int(nad)
            except (TypeError, ValueError):
                unmatched += 1
                continue
            fid = lookup.get(nid)
            if fid is None:
                unmatched += 1
                continue
            geom_j = feat.get("geometry")
            if not geom_j:
                bad_geom += 1
                continue
            try:
                g = shape(geom_j)
            except Exception:
                bad_geom += 1
                continue
            c = g.centroid if g.geom_type in ("Polygon", "MultiPolygon") else None
            if c is None or c.is_empty:
                bad_geom += 1
                continue
            records.append({"feature_id": fid, "geometry": Point(c.x, c.y)})
        if records and not ns.dry_run:
            gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
            gdf = gdf.rename(columns={"geometry": "geom"}).set_geometry("geom")
            gdf["source_note"] = "kansas_dasc_arcgis_PLSS_View"
            gdf.to_postgis(
                "ks_plss_section_site",
                eng,
                if_exists="append",
                index=False,
            )
            total_written += len(records)
        elif records and ns.dry_run:
            total_written += len(records)

        print(f"  offset={offset} batch_features={len(feats)} matched_centroids={len(records)}", flush=True)

        offset += len(feats)
        batch_i += 1
        if ns.max_batches is not None and batch_i >= ns.max_batches:
            break

    if not ns.dry_run:
        _enrich_site_table(eng)

    with eng.connect() as conn:
        n_db = conn.execute(text("SELECT count(*) FROM ks_plss_section_site")).scalar()
    print(
        f"Done. ks_plss_section_site rows={n_db} (written batches total_centroids≈{total_written}), "
        f"unmatched_attrs={unmatched}, bad_geom={bad_geom}"
    )
    if not ns.dry_run and n_db and n_db < len(lookup):
        print(
            f"Warning: site count {n_db} < ks_plss_section rows {len(lookup)} — check unmatched.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
