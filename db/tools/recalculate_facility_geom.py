#!/usr/bin/env python3
"""
Recalculate facility geometry (geom) from latitude/longitude in public.facility.

Behavior:
- Finds facilities with latitude/longitude but missing or incorrect geom
- Updates geom using ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
- Skips facilities where geom already matches lat/lon (unless --overwrite)
- Supports filtering and limiting

DB config:
- Loaded from .env via python-dotenv using:
  POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGIS_HOST_PORT
Optional:
  PGHOST (default localhost)

Safety:
- Default is DRY RUN unless you pass --apply
"""

import os
import argparse
from typing import List, Dict, Any, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# DB helpers
# ----------------------------

def db_connect():
    """
    Uses .env variables:
      POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGIS_HOST_PORT
    Optional:
      PGHOST (default localhost)
    """
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("POSTGIS_HOST_PORT")
    if not port:
        raise SystemExit("ERROR: POSTGIS_HOST_PORT is not set in .env")

    for k in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if not os.environ.get(k):
            raise SystemExit(f"ERROR: {k} is not set in .env")

    return psycopg2.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=host,
        port=port,
    )


def fetch_facilities(conn, limit: int, where_sql: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch facilities that need geom recalculation.
    """
    base_where = """
        latitude IS NOT NULL 
        AND longitude IS NOT NULL
        AND (
            geom IS NULL 
            OR ABS(ST_X(geom) - longitude::DOUBLE PRECISION) > 0.000001
            OR ABS(ST_Y(geom) - latitude::DOUBLE PRECISION) > 0.000001
        )
    """
    
    if where_sql:
        where_clause = f"{base_where} AND ({where_sql})"
    else:
        where_clause = base_where
    
    sql = f"""
        SELECT
            facility_id,
            name,
            city,
            state,
            latitude,
            longitude,
            geom,
            CASE 
                WHEN geom IS NULL THEN 'MISSING'
                ELSE 'MISMATCH'
            END as issue_type
        FROM public.facility
        WHERE {where_clause}
        ORDER BY facility_id
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (limit,))
        return list(cur.fetchall())


def update_facility_geom(conn, facility_id: int, latitude: float, longitude: float):
    """
    Update facility geom from lat/lon.
    """
    sql = """
        UPDATE public.facility
        SET geom = ST_SetSRID(
            ST_MakePoint(%s::DOUBLE PRECISION, %s::DOUBLE PRECISION),
            4326
        )
        WHERE facility_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (longitude, latitude, facility_id))


def count_total_facilities(conn, where_sql: Optional[str] = None) -> Dict[str, int]:
    """
    Get counts of facilities with various geom states.
    """
    base_where = "latitude IS NOT NULL AND longitude IS NOT NULL"
    
    if where_sql:
        where_clause = f"{base_where} AND ({where_sql})"
    else:
        where_clause = base_where
    
    sql = f"""
        SELECT 
            COUNT(*) as total,
            COUNT(geom) as with_geom,
            COUNT(*) FILTER (WHERE geom IS NULL) as missing_geom,
            COUNT(*) FILTER (
                WHERE geom IS NOT NULL 
                AND (
                    ABS(ST_X(geom) - longitude::DOUBLE PRECISION) > 0.000001
                    OR ABS(ST_Y(geom) - latitude::DOUBLE PRECISION) > 0.000001
                )
            ) as mismatched_geom
        FROM public.facility
        WHERE {where_clause}
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return dict(cur.fetchone())


def main():
    parser = argparse.ArgumentParser(
        description="Recalculate facility geometry from latitude/longitude."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (otherwise dry run)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max facilities to process (0=all)"
    )
    parser.add_argument(
        "--where",
        type=str,
        default=None,
        help="Custom SQL WHERE clause (without 'WHERE') to filter facilities"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite geom even if it matches lat/lon (processes all facilities with lat/lon)"
    )
    args = parser.parse_args()

    conn = db_connect()
    conn.autocommit = False

    try:
        # Get statistics
        print("Recalculate Facility Geometry")
        print("=" * 60)
        stats = count_total_facilities(conn, args.where)
        print(f"\nStatistics:")
        print(f"  Total facilities with lat/lon: {stats['total']}")
        print(f"  With geom: {stats['with_geom']}")
        print(f"  Missing geom: {stats['missing_geom']}")
        print(f"  Mismatched geom: {stats['mismatched_geom']}")
        
        if args.overwrite:
            print(f"\n⚠️  --overwrite mode: Will update all {stats['total']} facilities with lat/lon")
            # Adjust WHERE clause to include all facilities with lat/lon
            overwrite_where = "latitude IS NOT NULL AND longitude IS NOT NULL"
            if args.where:
                combined_where = f"{overwrite_where} AND ({args.where})"
            else:
                combined_where = overwrite_where
            
            # Fetch all facilities with lat/lon (respecting limit and where)
            sql = f"""
                SELECT
                    facility_id,
                    name,
                    city,
                    state,
                    latitude,
                    longitude,
                    geom,
                    'OVERWRITE' as issue_type
                FROM public.facility
                WHERE {combined_where}
                ORDER BY facility_id
            """
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if args.limit > 0:
                    sql += " LIMIT %s"
                    cur.execute(sql, (args.limit,))
                else:
                    cur.execute(sql)
                facilities = list(cur.fetchall())
        else:
            # Normal mode: only facilities with missing/mismatched geom
            limit = args.limit if args.limit > 0 else 999999
            facilities = fetch_facilities(conn, limit, args.where)
        
        if not facilities:
            print("\n✅ No facilities need geom recalculation.")
            return
        
        print(f"\nProcessing {len(facilities)} facility/facilities...")
        
        if not args.apply:
            print("\n🔍 DRY RUN mode - no changes will be made")
            print("Re-run with --apply to execute changes\n")
        
        updated = 0
        skipped = 0
        errors = 0
        
        for i, facility in enumerate(facilities, start=1):
            fid = facility["facility_id"]
            name = facility["name"]
            city = facility.get("city") or ""
            state = facility.get("state") or ""
            lat = float(facility["latitude"])
            lon = float(facility["longitude"])
            issue = facility["issue_type"]
            
            print(f"\n[{i}/{len(facilities)}] facility_id={fid}: {name}")
            if city or state:
                print(f"  Location: {city}, {state}")
            print(f"  Coordinates: {lat}, {lon}")
            print(f"  Issue: {issue}")
            
            if args.apply:
                try:
                    update_facility_geom(conn, fid, lat, lon)
                    conn.commit()
                    print(f"  ✅ Updated geom successfully")
                    updated += 1
                except Exception as e:
                    conn.rollback()
                    print(f"  ❌ Error: {e}")
                    errors += 1
            else:
                print(f"  [DRY RUN] Would update geom")
                updated += 1
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        if args.apply:
            print(f"  Updated: {updated}")
            if errors > 0:
                print(f"  Errors: {errors}")
        else:
            print(f"  Would update: {updated}")
            print("  (Run with --apply to execute)")
        
        if not args.apply:
            print("\n⚠️  Ran in DRY RUN mode. Re-run with --apply to execute changes.")
    
    finally:
        conn.close()


if __name__ == "__main__":
    main()
