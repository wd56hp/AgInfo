"""
Management command to update facility geometries from addresses.
Connects to remote database at 172.16.101.20:15433 and geocodes addresses.
"""
import os
from django.core.management.base import BaseCommand
from django.db import connection
from django.contrib.gis.geos import Point
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from decouple import config
import time


class Command(BaseCommand):
    help = 'Update facility geometries from addresses using geocoding'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            type=str,
            default='172.16.101.20',
            help='Database host (default: 172.16.101.20)'
        )
        parser.add_argument(
            '--port',
            type=str,
            default='15433',
            help='Database port (default: 15433)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between geocoding requests in seconds (default: 1.0)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making database changes'
        )

    def handle(self, *args, **options):
        # Get database credentials from .env file or environment
        db_name = config('POSTGRES_DB', default='aginfo')
        db_user = config('POSTGRES_USER', default='agadmin')
        db_password = config('POSTGRES_PASSWORD', default='')
        db_host = options['host']
        db_port = options['port']
        delay = options['delay']
        dry_run = options['dry_run']
        
        # If password not found, try environment variable as fallback
        if not db_password:
            db_password = os.environ.get('POSTGRES_PASSWORD', '')

        self.stdout.write(f'Connecting to database: {db_host}:{db_port}/{db_name}')
        
        # Override database connection settings
        from django.conf import settings
        from django.db import connections
        
        # Update default database settings
        settings.DATABASES['default']['HOST'] = db_host
        settings.DATABASES['default']['PORT'] = db_port
        settings.DATABASES['default']['NAME'] = db_name
        settings.DATABASES['default']['USER'] = db_user
        settings.DATABASES['default']['PASSWORD'] = db_password

        # Close existing connection and reconnect with new settings
        connections['default'].close()
        connections['default'].settings_dict.update({
            'HOST': db_host,
            'PORT': db_port,
            'NAME': db_name,
            'USER': db_user,
            'PASSWORD': db_password,
        })

        # Test database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write(self.style.SUCCESS('Database connection successful'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to connect to database: {e}'))
            return

        # Initialize geocoder
        geolocator = Nominatim(user_agent="aginfo_geocoder")
        
        # Check if geom_from_address column exists, create if not
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='facility' AND column_name='geom_from_address'
            """)
            if not cursor.fetchone():
                self.stdout.write('Adding geom_from_address column to facility table...')
                if not dry_run:
                    cursor.execute("""
                        ALTER TABLE facility 
                        ADD COLUMN geom_from_address BOOLEAN DEFAULT FALSE
                    """)
                    self.stdout.write(self.style.SUCCESS('Column added successfully'))
                else:
                    self.stdout.write(self.style.WARNING('[DRY RUN] Would add column'))

        # Get facilities that need geocoding
        with connection.cursor() as cursor:
            # Find facilities with addresses but no geom_from_address flag set
            cursor.execute("""
                SELECT facility_id, name, address_line1, address_line2, 
                       city, county, state, postal_code, geom, geom_from_address
                FROM facility
                WHERE (address_line1 IS NOT NULL AND address_line1 != '')
                   OR (city IS NOT NULL AND city != '')
                ORDER BY facility_id
            """)
            facilities = cursor.fetchall()

        self.stdout.write(f'Found {len(facilities)} facilities with addresses')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        updated_count = 0
        failed_count = 0
        skipped_count = 0

        for facility in facilities:
            facility_id, name, addr1, addr2, city, county, state, postal, geom, geom_from_address = facility
            
            # Skip if already geocoded from address
            if geom_from_address:
                skipped_count += 1
                continue

            # Build address string
            address_parts = []
            if addr1:
                address_parts.append(addr1)
            if city:
                address_parts.append(city)
            if state:
                address_parts.append(state)
            if postal:
                address_parts.append(postal)
            
            if not address_parts:
                self.stdout.write(f'  Skipping {name} (facility_id={facility_id}): No address data')
                skipped_count += 1
                continue

            address_string = ', '.join(address_parts)
            self.stdout.write(f'  Geocoding {name} (facility_id={facility_id}): {address_string}')

            try:
                # Geocode the address
                location = geolocator.geocode(address_string, timeout=10)
                
                if location:
                    lat = location.latitude
                    lon = location.longitude
                    
                    self.stdout.write(f'    Found: {lat}, {lon}')
                    
                    if not dry_run:
                        # Update geometry and flag
                        point = Point(lon, lat, srid=4326)
                        with connection.cursor() as update_cursor:
                            update_cursor.execute("""
                                UPDATE facility 
                                SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                    latitude = %s,
                                    longitude = %s,
                                    geom_from_address = TRUE
                                WHERE facility_id = %s
                            """, [lon, lat, lat, lon, facility_id])
                        
                        self.stdout.write(self.style.SUCCESS(f'    Updated successfully'))
                        updated_count += 1
                    else:
                        self.stdout.write(self.style.WARNING(f'    [DRY RUN] Would update to: {lat}, {lon}'))
                        updated_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'    No location found'))
                    failed_count += 1

            except (GeocoderTimedOut, GeocoderServiceError) as e:
                self.stdout.write(self.style.ERROR(f'    Geocoding error: {e}'))
                failed_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    Unexpected error: {e}'))
                failed_count += 1

            # Rate limiting
            if delay > 0:
                time.sleep(delay)

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('Summary:')
        self.stdout.write(f'  Updated: {updated_count}')
        self.stdout.write(f'  Failed: {failed_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Total: {len(facilities)}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were saved'))
        else:
            self.stdout.write(self.style.SUCCESS('\nCompleted successfully!'))
