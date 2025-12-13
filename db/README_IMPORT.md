# Data Import Guide

This guide explains how to import SQL data files from the `db/temp` directory into the AgInfo PostgreSQL database.

## Directory Structure

- `db/temp/` - Place your SQL data files here
- `db/init/` - Initialization scripts (run automatically on first container start)
- `db/data/` - PostgreSQL data directory (Docker volume)

## File Naming

Files in `db/temp/` can be named with patterns like:
- `001-010*.sql` - Files matching this pattern
- `011*.sql` - Files matching this pattern
- `*.sql` - All SQL files

Files are imported in alphabetical order.

## Import Methods

### Method 1: Docker-based Import (Recommended)

This method uses the Docker container to import files. The `db/temp` directory is mounted as read-only into the container.

```bash
# Make script executable
chmod +x db/import_via_docker.sh

# Import files matching pattern (e.g., 011*)
./db/import_via_docker.sh "011*"

# Import all SQL files
./db/import_via_docker.sh "*.sql"
```

### Method 2: Direct Import (Host-based)

This method requires `psql` to be installed on the host machine and direct network access to the database.

```bash
# Make script executable
chmod +x db/import_data.sh

# Set environment variables (optional, defaults shown)
export POSTGRES_HOST=localhost
export POSTGRES_PORT=15433
export POSTGRES_DB=aginfo
export POSTGRES_USER=agadmin
export POSTGRES_PASSWORD=changeme

# Import files matching pattern
./db/import_data.sh "011*"
```

### Method 3: PowerShell (Windows)

If you're on Windows and have `psql` installed:

```powershell
# Import files matching pattern
.\db\import_data.ps1 -Pattern "011*"

# With custom settings
.\db\import_data.ps1 -Pattern "011*" -DbHost "172.16.101.20" -DbPort 15433
```

### Method 4: Manual Docker Exec

You can also manually import files using `docker exec`:

```bash
# List files in temp directory
docker exec aginfo-postgis ls -la /tmp/aginfo-import/

# Import a specific file
docker exec -i aginfo-postgis psql -U agadmin -d aginfo -f /tmp/aginfo-import/011_data.sql

# Import all files matching pattern
docker exec aginfo-postgis sh -c "for f in /tmp/aginfo-import/011*.sql; do echo \"Importing \$f\"; psql -U agadmin -d aginfo -f \"\$f\"; done"
```

## Environment Variables

You can customize the import scripts using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `15433` | Database port |
| `POSTGRES_DB` | `aginfo` | Database name |
| `POSTGRES_USER` | `agadmin` | Database user |
| `POSTGRES_PASSWORD` | `changeme` | Database password |
| `POSTGIS_CONTAINER` | `aginfo-postgis` | Docker container name |
| `TEMP_DIR` | `./db/temp` | Temp directory path (host-based script only) |

## Example Workflow

1. **Place your SQL files in `db/temp/`**:
   ```bash
   # On Unraid server at 172.16.101.20
   # Files should be in: /mnt/user/appdata/aginfo/db/temp/
   ```

2. **Import files matching pattern**:
   ```bash
   # SSH into your Unraid server or run from the AgInfo directory
   cd /path/to/AgInfo
   ./db/import_via_docker.sh "011*"
   ```

3. **Verify import**:
   ```bash
   # Connect to database and check
   docker exec -it aginfo-postgis psql -U agadmin -d aginfo
   # Then run: SELECT COUNT(*) FROM facility;
   ```

## Troubleshooting

### Container not found
- Make sure the Docker container is running: `docker ps | grep aginfo-postgis`
- Check container name: `docker ps --format '{{.Names}}'`

### Files not found
- Verify files are in `db/temp/` directory on the host
- Check file permissions: `ls -la db/temp/`
- Ensure files match the pattern you specified

### Connection errors
- Verify database is accessible: `docker exec aginfo-postgis pg_isready -U agadmin`
- Check port mapping in `docker-compose.yml`
- Verify credentials match your `.env` file or docker-compose defaults

### Import errors
- Check SQL file syntax: `docker exec aginfo-postgis psql -U agadmin -d aginfo -f /tmp/aginfo-import/yourfile.sql`
- Review PostgreSQL logs: `docker logs aginfo-postgis`
- Ensure tables exist (run `db/init/02_schema_aginfo.sql` first if needed)

## Notes

- Files in `db/temp/` are mounted as **read-only** in the container for safety
- Import scripts process files in alphabetical order
- Failed imports are reported at the end with a summary
- The scripts use `ON CONFLICT` handling where appropriate in SQL files

