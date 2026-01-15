#!/usr/bin/env python3
"""
Fix facility geolocations in public.facility.

Behavior:
- Tries to geocode using street address first (address_line1/address_line2 + city/state/zip).
- If street address is missing/unusable, falls back to "City, State (ZIP)".
- Normalizes common rural address issues: "CR" -> "County Road".
- Updates:
    - latitude
    - longitude
    - geom_from_address = TRUE
  (Assumes your DB trigger regenerates geom from lat/lon.)

Geocoder backends:
- Default: Nominatim (OpenStreetMap) - no API key
- Optional: Google Geocoding API if you set GOOGLE_API_KEY and use --use-google

DB config:
- Loaded from .env via python-dotenv using:
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    POSTGIS_HOST_PORT
  plus optional:
    PGHOST (defaults to localhost)
"""

import os
import re
import csv
import time
import argparse
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


# ----------------------------
# Load .env
# ----------------------------

# Try to load .env from current directory or parent directories
# Also check /project/.env (Docker mount path) if available
env_loaded = load_dotenv()
if not env_loaded and os.path.exists("/project/.env"):
    load_dotenv("/project/.env")


# ----------------------------
# Address cleaning / heuristics
# ----------------------------

CR_PATTERNS = [
    # Whole-token "CR" or common punctuated variants
    (re.compile(r"\bC\.?\s*R\.?\b", re.IGNORECASE), "County Road"),
    # Sometimes "Co Rd" or "Cty Rd"
    (re.compile(r"\bCo\.?\s*Rd\.?\b", re.IGNORECASE), "County Road"),
    (re.compile(r"\bCty\.?\s*Rd\.?\b", re.IGNORECASE), "County Road"),
]

BAD_STREET_MARKERS = {"", "n/a", "na", "none", "unknown", "null", "-", "--"}


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean_street(street: Optional[str]) -> Optional[str]:
    if street is None:
        return None
    s = normalize_whitespace(street)
    if s.lower() in BAD_STREET_MARKERS:
        return None

    # Replace CR variants with County Road
    for pat, repl in CR_PATTERNS:
        s = pat.sub(repl, s)

    # Extra safe normalization
    s = re.sub(r"\bCounty\s+Rd\b", "County Road", s, flags=re.IGNORECASE)

    return normalize_whitespace(s) if s else None


def looks_like_no_street(street: Optional[str]) -> bool:
    """Heuristic for missing/unusable street."""
    s = (street or "").strip().lower()
    if s in BAD_STREET_MARKERS:
        return True

    # If it has no digits and is very short, it's often not a deliverable street address
    has_digit = any(ch.isdigit() for ch in s)
    if (not has_digit) and len(s) < 6:
        return True

    return False


def build_queries(
    address_line1: Optional[str],
    address_line2: Optional[str],
    city: Optional[str],
    state: Optional[str],
    postal_code: Optional[str],
) -> List[Tuple[str, str]]:
    """
    Returns a list of (query, mode) where mode is 'address' or 'city_state'.
    We try address-based first, then fallback to city/state (center of town).
    """
    street1 = clean_street(address_line1)
    street2 = clean_street(address_line2)

    city_n = normalize_whitespace(city) if city else ""
    state_n = (state or "").strip().upper()
    postal_n = normalize_whitespace(postal_code) if postal_code else ""

    address_parts = [p for p in [street1, street2, city_n, state_n, postal_n] if p]
    city_state_parts = [p for p in [city_n, state_n, postal_n] if p]

    queries: List[Tuple[str, str]] = []

    # Prefer full address if we have something street-like
    if street1 and not looks_like_no_street(street1):
        queries.append((", ".join(address_parts), "address"))
        # Also include city_state as fallback
        if city_n and state_n:
            queries.append((", ".join(city_state_parts), "city_state"))
    # If no street address, use city/state (will geocode to center of town)
    elif city_n and state_n:
        queries.append((", ".join(city_state_parts), "city_state"))

    return queries


# ----------------------------
# Geocoding backends
# ----------------------------

@dataclass
class GeoResult:
    lat: float
    lon: float
    display_name: str
    raw: Optional[Dict[str, Any]] = None


class Geocoder:
    def geocode(self, query: str) -> Optional[GeoResult]:
        raise NotImplementedError


class NominatimGeocoder(Geocoder):
    """
    Free OSM geocoder. Requires a descriptive User-Agent.
    Respect rate limits (1 req/sec is recommended).
    """
    def __init__(self, user_agent: str, country_codes: str = "us", timeout: int = 20):
        self.session = requests.Session()
        self.user_agent = user_agent
        self.country_codes = country_codes
        self.timeout = timeout

    def geocode(self, query: str) -> Optional[GeoResult]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
            "countrycodes": self.country_codes,
        }
        headers = {"User-Agent": self.user_agent}
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        top = data[0]
        return GeoResult(
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            display_name=top.get("display_name", ""),
            raw=top,
        )


class GoogleGeocoder(Geocoder):
    def __init__(self, api_key: str, timeout: int = 20):
        self.session = requests.Session()
        self.api_key = api_key
        self.timeout = timeout

    def geocode(self, query: str) -> Optional[GeoResult]:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": query, "key": self.api_key}
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        top = data["results"][0]
        loc = top["geometry"]["location"]
        return GeoResult(
            lat=float(loc["lat"]),
            lon=float(loc["lng"]),
            display_name=top.get("formatted_address", ""),
            raw=top,
        )


# ----------------------------
# DB + processing
# ----------------------------

def db_connect():
    """
    Uses .env variables:
      POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGIS_HOST_PORT
    Optional:
      PGHOST (default localhost)
    """
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("POSTGIS_HOST_PORT")  # external port
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


def fetch_facilities(conn, limit: int, where_sql: str) -> List[Dict[str, Any]]:
    """
    Provide your own WHERE clause (without 'WHERE') to target 'bad' rows.
    """
    sql = f"""
        SELECT
            facility_id,
            name,
            address_line1, address_line2, city, state, postal_code,
            latitude, longitude,
            geom_from_address
        FROM public.facility
        WHERE {where_sql}
        ORDER BY facility_id
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (limit,))
        return list(cur.fetchall())


def update_facility(conn, facility_id: int, lat: float, lon: float):
    """
    Mark geom_from_address = TRUE whenever we successfully geocode.
    """
    sql = """
        UPDATE public.facility
        SET latitude = %s,
            longitude = %s,
            geom_from_address = TRUE
        WHERE facility_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (lat, lon, facility_id))


def is_obviously_bad_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return True
    if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        return True
    # common "null island" / zeros
    if abs(float(lat)) < 0.0001 and abs(float(lon)) < 0.0001:
        return True
    return False


def main():
    p = argparse.ArgumentParser(description="Fix facility geolocations by re-geocoding addresses.")
    p.add_argument("--limit", type=int, default=500, help="Max facilities to process")
    p.add_argument("--dry-run", action="store_true", help="Do not write updates, only log")
    p.add_argument("--sleep", type=float, default=1.1, help="Seconds to sleep between geocode calls")
    p.add_argument("--log-csv", default="facility_geofix_log.csv", help="Output CSV log")
    p.add_argument("--where", default=None, help="Custom SQL WHERE (without 'WHERE') to pick records")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing lat/lon values (processes all facilities, not just missing/bad ones)")
    p.add_argument("--geom-from-address-false", action="store_true", help="Only process facilities where geom_from_address = FALSE")
    p.add_argument("--marked", action="store_true", help="Only process facilities where marked = TRUE")
    p.add_argument("--not-updated-after", type=str, metavar="DATE", help="Only process facilities not updated after this date (YYYY-MM-DD format). Note: requires updated_at column in facility table.")
    p.add_argument("--use-google", action="store_true", help="Use Google Geocoding API (requires GOOGLE_API_KEY)")
    p.add_argument("--country-codes", default="us", help="Nominatim countrycodes filter (default us)")
    args = p.parse_args()

    # Check if updated_at column exists (for --not-updated-after flag)
    if args.not_updated_after:
        conn_check = db_connect()
        with conn_check.cursor() as cur:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'facility' 
                AND column_name = 'updated_at'
            """)
            if not cur.fetchone():
                conn_check.close()
                raise SystemExit("ERROR: --not-updated-after requires an 'updated_at' column in the facility table, but it doesn't exist.")
        conn_check.close()
    
    # Build WHERE clause from flags
    where_conditions = []
    
    # If custom WHERE provided, use it (but can combine with other flags)
    if args.where:
        where_conditions.append(f"({args.where})")
    
    # Add flag-based conditions
    if args.geom_from_address_false:
        where_conditions.append("geom_from_address = FALSE")
    
    if args.marked:
        where_conditions.append("marked = TRUE")
    
    if args.not_updated_after:
        where_conditions.append(f"updated_at < '{args.not_updated_after}'")
    
    # Default WHERE: missing or obviously bad lat/lon, unless --overwrite is set or other flags override
    if args.overwrite and not args.where and not args.geom_from_address_false and not args.marked and not args.not_updated_after:
        # Process all facilities when --overwrite is set without other filters
        where_sql = "1=1"
    elif where_conditions:
        # Combine all conditions with AND
        where_sql = " AND ".join(where_conditions)
    else:
        # Default: missing or obviously bad lat/lon
        where_sql = """
            (
              latitude IS NULL OR longitude IS NULL
              OR latitude = 0 OR longitude = 0
              OR latitude NOT BETWEEN -90 AND 90
              OR longitude NOT BETWEEN -180 AND 180
            )
        """

    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if args.use_google and not google_key:
        raise SystemExit("ERROR: --use-google set but GOOGLE_API_KEY env var is missing.")

    if args.use_google:
        geocoder: Geocoder = GoogleGeocoder(api_key=google_key)
        backend = "google"
    else:
        ua = os.environ.get(
            "NOMINATIM_USER_AGENT",
            "aginfo-geofix/1.0 (set NOMINATIM_USER_AGENT in env for production)"
        )
        geocoder = NominatimGeocoder(user_agent=ua, country_codes=args.country_codes)
        backend = "nominatim"

    conn = db_connect()
    conn.autocommit = False

    facilities = fetch_facilities(conn, args.limit, where_sql)
    total_facilities = len(facilities)
    
    if total_facilities == 0:
        print("No facilities found matching the criteria.")
        conn.close()
        return
    
    print(f"Processing {total_facilities} facilities...")

    with open(args.log_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "facility_id", "name",
            "mode_used", "query_used", "geocoder_backend",
            "old_lat", "old_lon", "new_lat", "new_lon",
            "old_geom_from_address", "new_geom_from_address",
            "display_name", "status"
        ])

        updated = 0
        skipped = 0
        processed = 0

        for row in facilities:
            processed += 1
            
            # Print progress every 25 records
            if processed % 25 == 0:
                print(f"Progress: {processed}/{total_facilities} ({100*processed//total_facilities}%) - Updated: {updated}, Skipped: {skipped}")
            fid = row["facility_id"]
            name = row.get("name") or ""
            old_lat = row.get("latitude")
            old_lon = row.get("longitude")
            old_gfa = row.get("geom_from_address")

            queries = build_queries(
                row.get("address_line1"),
                row.get("address_line2"),
                row.get("city"),
                row.get("state"),
                row.get("postal_code"),
            )

            if not queries:
                w.writerow([fid, name, "", "", backend, old_lat, old_lon, "", "", old_gfa, old_gfa, "", "NO_QUERY"])
                skipped += 1
                continue

            result: Optional[GeoResult] = None
            used_query = ""
            used_mode = ""

            for q, mode in queries:
                try:
                    r = geocoder.geocode(q)
                except Exception as e:
                    w.writerow([fid, name, mode, q, backend, old_lat, old_lon, "", "", old_gfa, old_gfa, "", f"ERROR: {e}"])
                    r = None

                time.sleep(args.sleep)

                if r is not None:
                    result = r
                    used_query = q
                    used_mode = mode
                    break

            if result is None:
                w.writerow([fid, name, "", "", backend, old_lat, old_lon, "", "", old_gfa, old_gfa, "", "NO_RESULT"])
                skipped += 1
                continue

            new_lat, new_lon = result.lat, result.lon
            new_gfa = True

            # If it was already good and is extremely close, skip (safety) unless --overwrite is set
            # Exception: Always update if using city_state mode (center of town geocoding)
            if (not args.overwrite) and (not is_obviously_bad_latlon(old_lat, old_lon)) and abs(float(old_lat) - new_lat) < 1e-6 and abs(float(old_lon) - new_lon) < 1e-6 and used_mode != "city_state":
                w.writerow([fid, name, used_mode, used_query, backend, old_lat, old_lon, new_lat, new_lon, old_gfa, old_gfa, result.display_name, "UNCHANGED"])
                skipped += 1
                continue

            if args.dry_run:
                w.writerow([fid, name, used_mode, used_query, backend, old_lat, old_lon, new_lat, new_lon, old_gfa, old_gfa, result.display_name, "DRY_RUN"])
                skipped += 1
                continue

            try:
                update_facility(conn, fid, new_lat, new_lon)
                conn.commit()
                w.writerow([fid, name, used_mode, used_query, backend, old_lat, old_lon, new_lat, new_lon, old_gfa, new_gfa, result.display_name, "UPDATED"])
                updated += 1
            except Exception as e:
                conn.rollback()
                w.writerow([fid, name, used_mode, used_query, backend, old_lat, old_lon, new_lat, new_lon, old_gfa, old_gfa, result.display_name, f"DB_ERROR: {e}"])
                skipped += 1
        
        # Print final summary
        print(f"\nDone. Processed: {processed}/{total_facilities}, Updated: {updated}, Skipped: {skipped}. Log: {args.log_csv}")

    conn.close()


if __name__ == "__main__":
    main()
