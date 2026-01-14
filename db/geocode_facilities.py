#!/usr/bin/env python3
"""
Geocode facilities using OpenStreetMap Nominatim API
- First tries full address (street, city, state, zip)
- Falls back to city, state if full address fails
- Updates latitude/longitude in database
- Geometry (geom) automatically updates via trigger
"""

import psycopg2
import time
import requests
import sys
import os

# Database connection parameters
DB_HOST = os.getenv('POSTGRES_HOST', '172.28.0.10')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_NAME = os.getenv('POSTGRES_DB', 'aginfo')
DB_USER = os.getenv('POSTGRES_USER', 'agadmin')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'changeme')

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_RATE_LIMIT = 1.0  # Seconds between requests

# Default coordinates (center of Kansas) - facilities with these need geocoding
DEFAULT_LAT = 38.5000
DEFAULT_LON = -98.0000


def geocode_address(address=None, city=None, state=None, zip_code=None):
    """Geocode an address using Nominatim API"""
    query_parts = []
    if address and address.strip():
        query_parts.append(address.strip())
    if city and city.strip():
        query_parts.append(city.strip())
    if state and state.strip():
        query_parts.append(state.strip())
    if zip_code and zip_code.strip():
        query_parts.append(zip_code.strip())
    
    query = ", ".join(query_parts)
    if not query:
        return None
    
    try:
        time.sleep(NOMINATIM_RATE_LIMIT)
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'us',
            'addressdetails': 1
        }
        headers = {
            'User-Agent': 'AgInfo Geocoding Script'
        }
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return (float(data[0]['lat']), float(data[0]['lon']))
    except Exception as e:
        print(f"  Error geocoding '{query}': {e}", file=sys.stderr)
    return None


def geocode_facility(facility):
    """Geocode facility - try full address first, then city/state"""
    address = facility.get('address_line1', '')
    city = facility.get('city', '')
    state = facility.get('state', '')
    zip_code = facility.get('postal_code', '')
    
    # Try full address
    if address and address.strip():
        coords = geocode_address(address, city, state, zip_code)
        if coords:
            print(f"  ✓ Full address")
            return coords
    
    # Try city/state
    if city and state:
        coords = geocode_address(None, city, state, None)
        if coords:
            print(f"  ✓ City/state")
            return coords
    
    print(f"  ✗ Failed")
    return None


def update_facility_coordinates(conn, facility_id, lat, lon):
    """Update facility coordinates in database"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE facility SET latitude = %s, longitude = %s WHERE facility_id = %s",
            (lat, lon, facility_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"  Error updating facility {facility_id}: {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()


def main():
    """Main geocoding process"""
    print("AgInfo Facility Geocoding")
    print("=" * 60)
    print(f"Database: {DB_NAME}@{DB_HOST}:{DB_PORT}")
    print(f"Using: OpenStreetMap Nominatim API")
    print("=" * 60)
    print()
    
    # Connect to database
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        cursor = conn.cursor()
        
        # Get facilities that need geocoding
        cursor.execute("""
            SELECT facility_id, name, address_line1, city, state, postal_code
            FROM facility
            WHERE notes LIKE '%KGFA%'
              AND latitude = %s
              AND longitude = %s
            ORDER BY state, city, name
        """, (38.5000, -98.0000))
        
        facilities = []
        for row in cursor.fetchall():
            facilities.append({
                'facility_id': row[0],
                'name': row[1],
                'address_line1': row[2],
                'city': row[3],
                'state': row[4],
                'postal_code': row[5]
            })
        
        cursor.close()
        
        total = len(facilities)
        print(f"Found {total} facilities needing geocoding")
        print()
        
        if total == 0:
            print("No facilities need geocoding!")
            return
        
        # Process each facility
        success_count = 0
        fail_count = 0
        
        for i, facility in enumerate(facilities, 1):
            facility_id = facility['facility_id']
            name = facility['name']
            city = facility['city'] or 'Unknown'
            state = facility['state'] or 'Unknown'
            
            print(f"[{i}/{total}] {name}, {city}, {state}")
            
            # Geocode the facility
            coords = geocode_facility(facility)
            
            if coords:
                lat, lon = coords
                try:
                    update_facility_coordinates(conn, facility_id, lat, lon)
                    success_count += 1
                    print(f"  Updated: ({lat:.6f}, {lon:.6f})")
                except Exception as e:
                    fail_count += 1
                    print(f"  Failed to update database: {e}")
            else:
                fail_count += 1
            
            print()
        
        # Summary
        print("=" * 60)
        print("Geocoding Summary:")
        print(f"  Total processed: {total}")
        print(f"  Successfully geocoded: {success_count}")
        print(f"  Failed: {fail_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
