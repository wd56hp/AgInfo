# Database Tools

This directory contains utility scripts for managing and fixing database data.

## Scripts

### facility_geom_from_address.py

Fixes facility geolocations by re-geocoding addresses from the database.

**Description:**
- Geocodes facilities using their address information
- Tries full street address first, falls back to city/state/zip (center of town) if no street address
- Normalizes common rural address issues (e.g., "CR" → "County Road")
- Updates `latitude`, `longitude`, and sets `geom_from_address = TRUE`
- Database trigger automatically regenerates `geom` from lat/lon
- When only city/state is available, geocodes to the center of the town/city

**Geocoder Backends:**
- **Default:** Nominatim (OpenStreetMap) - free, no API key required
- **Optional:** Google Geocoding API (requires `GOOGLE_API_KEY` environment variable)

**Usage:**
```bash
# Run via wrapper script (recommended)
./run_facility_geom_from_address.sh [options]

# Or directly (requires Python environment with dependencies)
python3 facility_geom_from_address.py [options]
```

**Flags:**
- `--limit LIMIT` - Maximum number of facilities to process (default: 500)
- `--dry-run` - Preview changes without updating the database
- `--sleep SLEEP` - Seconds to wait between geocode API calls (default: 1.1)
- `--log-csv LOG_CSV` - Output CSV log file path (default: facility_geofix_log.csv)
- `--where WHERE` - Custom SQL WHERE clause (without 'WHERE' keyword) to filter records
- `--overwrite` - Overwrite existing lat/lon values (processes all facilities, not just missing/bad ones)
- `--geom-from-address-false` - Only process facilities where `geom_from_address = FALSE`
- `--marked` - Only process facilities where `marked = TRUE`
- `--not-updated-after DATE` - Only process facilities not updated after this date (YYYY-MM-DD format). Requires `updated_at` column in facility table.
- `--use-google` - Use Google Geocoding API instead of Nominatim (requires `GOOGLE_API_KEY`)
- `--country-codes COUNTRY_CODES` - Nominatim country filter (default: "us")
- `-h, --help` - Show help message

**Environment Variables:**
Required (from `.env` file):
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password
- `POSTGIS_HOST_PORT` - Database port

Optional:
- `PGHOST` - Database host (default: localhost)
- `GOOGLE_API_KEY` - Required if using `--use-google`
- `NOMINATIM_USER_AGENT` - User agent string for Nominatim (recommended for production)

**Examples:**
```bash
# Dry run to see what would be updated
./run_facility_geom_from_address.sh --limit 10 --dry-run

# Fix only facilities with missing/bad coordinates (default behavior)
./run_facility_geom_from_address.sh --limit 100

# Re-geocode all facilities, overwriting existing coordinates
./run_facility_geom_from_address.sh --overwrite --limit 500

# Process only facilities where geom_from_address = FALSE
./run_facility_geom_from_address.sh --geom-from-address-false --limit 100

# Process only marked facilities
./run_facility_geom_from_address.sh --marked --limit 50

# Process facilities not updated after a specific date
./run_facility_geom_from_address.sh --not-updated-after 2024-01-01 --limit 200

# Combine flags: process marked facilities that haven't been geocoded
./run_facility_geom_from_address.sh --marked --geom-from-address-false --limit 100

# Process specific facilities using custom WHERE clause
./run_facility_geom_from_address.sh --where "facility_id IN (1, 2, 3)"

# Use Google Geocoding API
./run_facility_geom_from_address.sh --use-google --limit 50
```

**Output:**
- Creates a CSV log file with details of each processed facility
- Log includes: facility_id, name, query used, old/new coordinates, status
- Status values: `UPDATED`, `DRY_RUN`, `NO_QUERY`, `NO_RESULT`, `UNCHANGED`, `ERROR`, `DB_ERROR`

**Default Behavior:**
By default, the script only processes facilities with:
- Missing latitude or longitude (`NULL`)
- Zero coordinates (0, 0)
- Invalid coordinate ranges (outside -90 to 90 for lat, -180 to 180 for lon)

Use `--overwrite` to process all facilities regardless of existing coordinates.

---

### merg_duplicates.py

Interactive tool for merging duplicate companies and facilities in the database.

**Description:**
- **Phase A (Companies)**: Merges duplicate companies by repointing all foreign keys to a canonical company record
  - Normalizes company names (removes suffixes like "Inc.", "LLC", etc.)
  - Combines website, phone, and notes from duplicate records
  - Optionally archives old companies to `public.deactivated_companies` if that table exists
- **Phase B (Facilities)**: Merges duplicate facilities by creating a new canonical facility record
  - Groups facilities by normalized address (address + city + state + postal code)
  - Uses spatial distance (PostGIS) to split groups that are too far apart
  - Creates a new facility record with merged data from duplicates
  - Archives original facilities to `public.deactivated_facilities` (if table exists)
  - Sets original facilities to `INACTIVE` status
  - Repoints all foreign keys from old facility_ids to the new facility_id
- **Safety**: Default is DRY RUN mode - no changes are made unless `--apply` is used
- **Interactive**: Prompts for confirmation before each merge operation
- **Auto-discovery**: Automatically finds all foreign key references using PostgreSQL catalog

**Usage:**
```bash
# Run via wrapper script (recommended)
./run_merg_duplicates.sh [options]

# Or directly (requires Python environment with dependencies)
python3 merg_duplicates.py [options]
```

**Flags:**
- `--apply` - Apply changes to database (default is dry run mode)
- `--max-meters FLOAT` - Maximum distance in meters to keep facilities in the same group (default: 250.0)
- `--limit-companies INT` - Limit number of company groups to review (0 = all, default: 0)
- `--limit-facilities INT` - Limit number of facility groups to review (0 = all, default: 0)
- `-h, --help` - Show help message

**Environment Variables:**
Required (from `.env` file):
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password
- `POSTGIS_HOST_PORT` - Database port

Optional:
- `PGHOST` - Database host (default: localhost)

**Examples:**
```bash
# Dry run - preview what would be merged (default)
./run_merg_duplicates.sh

# Dry run with limits to test on a subset
./run_merg_duplicates.sh --limit-companies 5 --limit-facilities 10

# Apply changes (actually merge duplicates)
./run_merg_duplicates.sh --apply

# Use larger distance threshold for facility grouping (500 meters)
./run_merg_duplicates.sh --max-meters 500.0 --apply

# Test on limited subset before full run
./run_merg_duplicates.sh --limit-companies 2 --limit-facilities 5 --apply
```

**How It Works:**

1. **Company Merging (Phase A)**:
   - Groups companies by normalized name (removes suffixes, punctuation)
   - For each duplicate group, selects the "best" record (most complete data)
   - Merges website, phone, and notes from all duplicates
   - Repoints all foreign keys (from `facility.company_id`, etc.) to the canonical company
   - Optionally archives old companies if `public.deactivated_companies` table exists

2. **Facility Merging (Phase B)**:
   - Groups facilities by normalized address key (address + city + state + postal)
   - Uses PostGIS to calculate distances between facilities with same address
   - Splits groups if facilities are more than `--max-meters` apart
   - Creates a new facility record with merged data:
     - Name: longest/most specific name
     - Address: best available address data
     - Coordinates: prefers records with `geom_from_address = TRUE`
     - Contact info: first non-empty value
     - Text fields: combines descriptions, notes, imported_source
   - Archives original facilities to `public.deactivated_facilities` (if exists)
   - Sets original facilities to `INACTIVE` status
   - Repoints all foreign keys (from `facility_contact`, `facility_service`, etc.) to new facility

**Safety Features:**
- Default is DRY RUN mode - no database changes unless `--apply` is specified
- Interactive prompts ask for confirmation before each merge
- Shows detailed diff of what will change before applying
- Uses database transactions - rolls back on errors
- Auto-discovers foreign key relationships (no manual configuration needed)

**Required Tables:**
- `public.company` - Company records
- `public.facility` - Facility records
- Foreign key tables: `facility_contact`, `facility_service`, `facility_product`, `facility_transport_mode`, etc.

**Optional Tables (for archiving):**
- `public.deactivated_companies` - If exists, old companies are archived here
- `public.deactivated_facilities` - If exists, old facilities are archived here

**Notes:**
- Company merging happens first, then facility merging
- Facility merging creates NEW facility records (doesn't reuse existing IDs)
- All foreign key relationships are automatically discovered and updated
- Address normalization handles common rural address issues (e.g., "CR" → "County Road")
