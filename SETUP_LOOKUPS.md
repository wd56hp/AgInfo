# Lookups.json Setup and Automation

This document explains how `web/data/lookups.json` is automatically generated and updated.

## Overview

`lookups.json` is a generated file that contains:
- Company names (from `company` table)
- Facility type names (from `facility_type` table)
- Company website URLs (from `company.website_url`)

This file is **not** tracked in git (it's in `.gitignore`) and is automatically created/updated from the database.

## Scripts

### 1. `update_lookups.sh`
Main script that queries the database and updates `lookups.json`.
- Auto-detects if running on server (`/mnt/user/appdata/AgInfo`) or locally
- Creates the file and directory if they don't exist
- Can be run manually anytime: `./update_lookups.sh`

### 2. `init_lookups.sh`
Initialization script for new installations.
- Checks if `lookups.json` exists
- If missing, runs `update_lookups.sh` to create it
- Creates empty structure if database isn't ready

### 3. `web-container-startup.sh`
Runs when the web container starts.
- Waits for database to be ready
- Calls `init_lookups.sh` (which will create or update the file)
- Handles both new installs and existing installations

### 4. `docker-compose-up.sh`
Wrapper script for `docker-compose up`.
- Starts all containers
- Waits for web container to be ready
- Runs `web-container-startup.sh` automatically

## Usage

### Manual Start (Recommended)
Use the wrapper script instead of `docker-compose up`:
```bash
./docker-compose-up.sh
```

Or manually run after starting containers:
```bash
docker-compose up -d
./web-container-startup.sh
```

### Manual Update
To manually update lookups.json anytime:
```bash
./update_lookups.sh
```

### New Installation
For new installations, the file will be created automatically when you:
1. Start the containers: `./docker-compose-up.sh`
2. Or run: `./init_lookups.sh`

## Automatic Execution on Container Restart

The web container has `restart: unless-stopped`, so it will restart automatically after server reboots. To ensure `lookups.json` is updated on container restart, you have two options:

### Option 1: Systemd Service (Recommended for Production)
1. Copy the service file:
   ```bash
   sudo cp aginfo-web-startup.service /etc/systemd/system/
   ```
2. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable aginfo-web-startup.service
   sudo systemctl start aginfo-web-startup.service
   ```

### Option 2: Cron Job
Add to crontab to check and update periodically:
```bash
# Run every 5 minutes to update lookups if container is running
*/5 * * * * /mnt/user/appdata/AgInfo/web-container-startup.sh >/dev/null 2>&1
```

### Option 3: Docker Exec Hook (Alternative)
You can also monitor the container and run the script when it starts:
```bash
# Add to /etc/rc.local or a startup script
docker events --filter 'container=aginfo-web' --filter 'event=start' --format '{{.Time}}' | while read; do
    /mnt/user/appdata/AgInfo/web-container-startup.sh
done &
```

## File Locations

- **Server**: `/mnt/user/appdata/AgInfo/web/data/lookups.json`
- **Local**: `./web/data/lookups.json`
- Scripts auto-detect the environment

## Troubleshooting

### File not created
1. Check database is running: `docker ps | grep aginfo-postgis`
2. Check database is ready: `docker exec aginfo-postgis pg_isready -U agadmin -d aginfo`
3. Run manually: `./init_lookups.sh`

### File not updating
1. Check script permissions: `chmod +x update_lookups.sh init_lookups.sh web-container-startup.sh`
2. Run manually: `./update_lookups.sh`
3. Check logs: Scripts output to stdout/stderr

### Container restarts but file doesn't update
- Use Option 1 (systemd service) or Option 2 (cron) above
- Or manually run `./web-container-startup.sh` after container starts

