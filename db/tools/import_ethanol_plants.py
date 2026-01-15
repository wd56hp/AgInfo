#!/usr/bin/env python3
"""
Import ethanol plants from CSV file into the database.

Creates companies if they don't exist, then creates facilities.
Assumes CSV has columns for company name, facility name, address, city, state, etc.

Usage:
    python import_ethanol_plants.py <csv_file_path> [--apply]

Example:
    python import_ethanol_plants.py "C:/Users/will.darrah/OneDrive - Darrah Oil/ethonal.csv" --apply
"""

import os
import sys
import csv
import argparse
import time
import requests
from typing import Dict, Any, Optional, List, Tuple
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load .env
env_loaded = load_dotenv()
if not env_loaded and os.path.exists("/project/.env"):
    load_dotenv("/project/.env")


def db_connect():
    """Connect to database using .env variables."""
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


def get_or_create_facility_type(conn, name: str = "Ethanol Plant") -> int:
    """Get facility_type_id for Ethanol Plant, create if doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT facility_type_id FROM facility_type WHERE name = %s
            """,
            (name,)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        
        # Create it
        cur.execute(
            """
            INSERT INTO facility_type (name, description, is_producer, is_consumer, is_storage)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING facility_type_id
            """,
            (name, "Ethanol production facility", True, True, False)
        )
        facility_type_id = cur.fetchone()[0]
        conn.commit()
        print(f"✓ Created facility type: {name} (ID: {facility_type_id})", flush=True)
        return facility_type_id


def get_or_create_company(conn, company_name: str, website_url: Optional[str] = None,
                         phone_main: Optional[str] = None) -> tuple[int, bool]:
    """Get company_id for company, create if doesn't exist.
    
    Returns:
        (company_id, was_created) tuple where was_created is True if newly created
    """
    if not company_name or not company_name.strip():
        raise ValueError("Company name cannot be empty")
    
    company_name = company_name.strip()
    
    with conn.cursor() as cur:
        # Check if exists
        cur.execute(
            """
            SELECT company_id FROM company WHERE name = %s
            """,
            (company_name,)
        )
        row = cur.fetchone()
        if row:
            return (row[0], False)
        
        # Create it
        cur.execute(
            """
            INSERT INTO company (name, website_url, phone_main)
            VALUES (%s, %s, %s)
            RETURNING company_id
            """,
            (company_name, website_url, phone_main)
        )
        company_id = cur.fetchone()[0]
        conn.commit()
        print(f"  ✓ Created company: {company_name} (ID: {company_id})", flush=True)
        return (company_id, True)


def normalize_value(value: Optional[str]) -> Optional[str]:
    """Normalize string value - strip whitespace, return None if empty."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def parse_float(value: Optional[str]) -> Optional[float]:
    """Parse float from string, return None if invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def geocode_location(company_name: str, location: str) -> Optional[Tuple[float, float]]:
    """Geocode a location using Nominatim (OpenStreetMap).
    
    Returns (latitude, longitude) or None if geocoding fails.
    """
    if not company_name or not location:
        return None
    
    # Build search query: company name + location (state/province)
    query = f"{company_name}, {location}, USA"
    
    try:
        # Use Nominatim geocoding service (free, no API key needed)
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1
        }
        headers = {
            'User-Agent': 'AgInfo-Import-Script/1.0'  # Required by Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and len(data) > 0:
            result = data[0]
            lat = float(result.get('lat', 0))
            lon = float(result.get('lon', 0))
            if lat != 0 and lon != 0:
                # Rate limiting: be nice to Nominatim
                time.sleep(1)
                return (lat, lon)
    except Exception as e:
        print(f"    ⚠ Geocoding failed for {query}: {e}", flush=True)
    
    return None


def create_facility(conn, company_id: int, facility_type_id: int, row: Dict[str, Any],
                   apply: bool = False) -> Optional[int]:
    """Create a facility record from CSV row data."""
    
    # Extract data from row - try common column name variations
    # For ethanol plants CSV, "Name" is company name, so we'll create facility name from company + location
    company_name_for_facility = (
        normalize_value(row.get('name')) or
        normalize_value(row.get('company_name')) or
        normalize_value(row.get('company')) or
        "Unknown Company"
    )
    location = normalize_value(row.get('location')) or ''
    
    facility_name = (
        normalize_value(row.get('facility_name')) or
        normalize_value(row.get('plant_name')) or
        f"{company_name_for_facility} - {location}".strip(' -') if location else company_name_for_facility
    )
    
    address_line1 = (
        normalize_value(row.get('address')) or
        normalize_value(row.get('address_line1')) or
        normalize_value(row.get('street')) or
        normalize_value(row.get('address1'))
    )
    
    # For ethanol CSV, "Location" is state/province code
    location_code = normalize_value(row.get('location')) or ''
    city = normalize_value(row.get('city'))
    state = normalize_value(row.get('state')) or location_code or 'KS'  # Use location if state not provided
    postal_code = normalize_value(row.get('zip')) or normalize_value(row.get('postal_code')) or normalize_value(row.get('zipcode'))
    county = normalize_value(row.get('county'))
    
    latitude = parse_float(row.get('latitude')) or parse_float(row.get('lat'))
    longitude = parse_float(row.get('longitude')) or parse_float(row.get('lon')) or parse_float(row.get('lng'))
    
    # If coordinates not provided, try to geocode from company name + location
    if not latitude or not longitude:
        print(f"  ⚠ No coordinates found, attempting geocoding...", flush=True)
        coords = geocode_location(company_name_for_facility, location)
        if coords:
            latitude, longitude = coords
            print(f"  ✓ Geocoded coordinates: {latitude}, {longitude}", flush=True)
        else:
            print(f"  ⚠ Skipping {facility_name}: could not geocode location", flush=True)
            return None
    
    website_url = normalize_value(row.get('link')) or normalize_value(row.get('website')) or normalize_value(row.get('website_url'))
    phone_main = normalize_value(row.get('phone')) or normalize_value(row.get('phone_main'))
    email_main = normalize_value(row.get('email')) or normalize_value(row.get('email_main'))
    
    # Build notes from available data
    notes_parts = []
    if normalize_value(row.get('feedstock')):
        notes_parts.append(f"Feedstock: {normalize_value(row.get('feedstock'))}")
    if normalize_value(row.get('rins')):
        notes_parts.append(f"RINs: {normalize_value(row.get('rins'))}")
    capacity_key = 'capacity (mmgy)'
    if normalize_value(row.get(capacity_key)):
        notes_parts.append(f"Capacity: {normalize_value(row.get(capacity_key))} MMgy")
    notes = '; '.join(notes_parts) if notes_parts else (normalize_value(row.get('notes')) or normalize_value(row.get('description')))
    
    # Coordinates should be set by now (either from CSV or geocoding)
    # This check is just a safety net
    if not latitude or not longitude:
        print(f"  ⚠ Skipping {facility_name}: missing latitude/longitude", flush=True)
        return None
    
    if not state:
        state = 'KS'  # Default to Kansas
    
    # Check if facility already exists (by name + city + state)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT facility_id FROM facility
            WHERE name = %s AND city = %s AND state = %s
            """,
            (facility_name, city or '', state)
        )
        existing = cur.fetchone()
        if existing:
            print(f"  ⊙ Facility already exists: {facility_name} in {city}, {state} (ID: {existing[0]})", flush=True)
            return existing[0]
        
        if apply:
            cur.execute(
                """
                INSERT INTO facility (
                    company_id, facility_type_id, name, description,
                    address_line1, city, county, state, postal_code,
                    latitude, longitude,
                    website_url, phone_main, email_main, notes,
                    status
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    'ACTIVE'
                )
                RETURNING facility_id
                """,
                (
                    company_id, facility_type_id, facility_name, notes,
                    address_line1, city, county, state, postal_code,
                    latitude, longitude,
                    website_url, phone_main, email_main, notes,
                )
            )
            facility_id = cur.fetchone()[0]
            conn.commit()
            print(f"  ✓ Created facility: {facility_name} (ID: {facility_id})", flush=True)
            return facility_id
        else:
            print(f"  [DRY RUN] Would create facility: {facility_name} in {city}, {state}", flush=True)
            return None


def read_csv_file(file_path: str) -> List[Dict[str, Any]]:
    """Read CSV file and return list of dictionaries."""
    rows = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # Try to detect delimiter
            sample = f.read(1024)
            f.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Normalize keys to lowercase for easier access
                normalized_row = {k.lower().strip(): v for k, v in row.items()}
                rows.append(normalized_row)
    except FileNotFoundError:
        raise SystemExit(f"ERROR: File not found: {file_path}")
    except Exception as e:
        raise SystemExit(f"ERROR reading CSV file: {e}")
    
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Import ethanol plants from CSV file into database"
    )
    parser.add_argument(
        'csv_file',
        help='Path to CSV file containing ethanol plant data'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Actually apply changes to database (default is dry run)'
    )
    
    args = parser.parse_args()
    
    if not args.apply:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made to database")
        print("=" * 60)
        print()
    
    # Read CSV
    print(f"Reading CSV file: {args.csv_file}", flush=True)
    rows = read_csv_file(args.csv_file)
    print(f"Found {len(rows)} rows in CSV", flush=True)
    
    if len(rows) == 0:
        print("No data to import")
        return
    
    # Show first row as sample
    print("\nSample row (first row):", flush=True)
    for key, value in list(rows[0].items())[:10]:
        print(f"  {key}: {value}", flush=True)
    print(flush=True)
    
    # Connect to database
    print("Connecting to database...", flush=True)
    conn = db_connect()
    print("✓ Connected", flush=True)
    
    try:
        # Get or create Ethanol Plant facility type
        print("\nChecking facility type...", flush=True)
        facility_type_id = get_or_create_facility_type(conn, "Ethanol Plant")
        print(f"Using facility_type_id: {facility_type_id}", flush=True)
        
        # Process each row
        print(f"\nProcessing {len(rows)} rows...", flush=True)
        print("-" * 60, flush=True)
        
        created_companies = 0
        created_facilities = 0
        skipped = 0
        
        for i, row in enumerate(rows, 1):
            print(f"\n[{i}/{len(rows)}] Processing row...", flush=True)
            
            # Get company name - try common variations
            # Note: CSV has "Name" column which is the company name
            company_name = (
                normalize_value(row.get('name')) or
                normalize_value(row.get('company_name')) or
                normalize_value(row.get('company')) or
                normalize_value(row.get('owner')) or
                normalize_value(row.get('operator'))
            )
            
            if not company_name:
                print(f"  ⚠ Skipping row {i}: no company name found", flush=True)
                skipped += 1
                continue
            
            # Get or create company
            company_website = normalize_value(row.get('company_website')) or normalize_value(row.get('company_website_url'))
            company_phone = normalize_value(row.get('company_phone')) or normalize_value(row.get('company_phone_main'))
            
            company_id, was_created = get_or_create_company(
                conn, company_name,
                website_url=company_website,
                phone_main=company_phone
            )
            
            if was_created:
                created_companies += 1
            
            # Create facility
            facility_id = create_facility(
                conn, company_id, facility_type_id, row, apply=args.apply
            )
            
            if facility_id:
                created_facilities += 1
        
        # Summary
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"Rows processed: {len(rows)}")
        print(f"Companies created: {created_companies}")
        print(f"Facilities created: {created_facilities}")
        print(f"Skipped: {skipped}")
        
        if not args.apply:
            print("\nThis was a DRY RUN. Use --apply to actually import data.")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
