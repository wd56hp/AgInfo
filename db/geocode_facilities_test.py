#!/usr/bin/env python3
"""
Test version - Geocode only first 5 facilities
Quick test to verify geocoding works before running on all 544 facilities
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
NOMINATIM_RATE_LIMIT = 1.0

def geocode_address(address: str, city: str = None, state: str = None, zip_code: str = None):
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
        params = {'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'us', 'addressdetails': 1}
        headers = {'User-Agent': 'AgInfo Geocoding Script'}
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return (float(data[0]['lat']), float(data[0]['lon']))
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
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
    
    return None

def main():
    print("AgInfo Facility Geocoding - TEST MODE (5 facilities only)")
    print("=" * 60)
    
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT facility_id, name, address_line1, city, state, postal_code
        FROM facility
        WHERE notes LIKE '%KGFA%' AND latitude = 38.5000 AND longitude = -98.0000
        ORDER BY state, city, name
        LIMIT 5
    """)
    
    facilities = [{'facility_id': r[0], 'name': r[1], 'address_line1': r[2], 
                   'city': r[3], 'state': r[4], 'postal_code': r[5]} for r in cursor.fetchall()]
    cursor.close()
    
    print(f"Testing with {len(facilities)} facilities\n")
    
    success = 0
    for i, fac in enumerate(facilities, 1):
        print(f"[{i}/{len(facilities)}] {fac['name']}, {fac['city']}, {fac['state']}")
        coords = geocode_facility(fac)
        if coords:
            lat, lon = coords
            cursor = conn.cursor()
            cursor.execute("UPDATE facility SET latitude = %s, longitude = %s WHERE facility_id = %s",
                          (lat, lon, fac['facility_id']))
            conn.commit()
            cursor.close()
            success += 1
            print(f"  Updated: ({lat:.6f}, {lon:.6f})\n")
        else:
            print(f"  ✗ Failed\n")
    
    print("=" * 60)
    print(f"Test Complete: {success}/{len(facilities)} geocoded successfully")
    print("If successful, run: ./geocode_facilities.sh")
    
    conn.close()

if __name__ == '__main__':
    main()
