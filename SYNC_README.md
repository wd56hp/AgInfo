# Unraid Sync Workflow

This project uses direct file sync to Unraid for testing without needing to commit every change.

## Quick Start

### 1. Pull ignored files from Unraid (one-time setup)
```bash
# Bash/Git Bash
bash unraid_pull.sh

# PowerShell (Windows)
.\unraid_pull.ps1
```

This will pull `.env` and other ignored files from the Unraid server to your local workstation.

### 2. Sync code to Unraid for testing
```bash
# Bash/Git Bash
bash unraid_sync.sh

# PowerShell (Windows) - requires rsync, or use Git Bash
.\unraid_sync.ps1
```

This syncs your local code (excluding gitignored files) to the Unraid server.

### 3. Restart services on Unraid
```bash
ssh root@172.16.101.20 "cd /mnt/user/appdata/AgInfo && docker-compose down && docker-compose up -d"
```

Or create a script `unraid_restart.sh`:
```bash
#!/usr/bin/env bash
ssh root@172.16.101.20 "cd /mnt/user/appdata/AgInfo && docker-compose down && docker-compose up -d"
```

## Workflow

1. **Make changes locally** in Cursor/your editor
2. **Sync to Unraid**: `bash unraid_sync.sh`
3. **Test on Unraid**: SSH in and restart services or test
4. **Repeat** until it works
5. **Commit** only when you're happy with the changes

## What Gets Synced

The sync script excludes:
- `.git/` directory
- `.env` file (stays on server)
- `db/data/` (Docker volumes, large)
- `geoserver/data_dir/` (Docker volumes, large)
- Build artifacts (`__pycache__`, `*.pyc`, `node_modules`, etc.)
- OS files (`.DS_Store`, `Thumbs.db`)

Everything else is synced, including:
- Source code
- Configuration files (except `.env`)
- Docker compose files
- Scripts
- Documentation

## Requirements

- `rsync` (usually pre-installed on Linux/Mac, or use Git Bash on Windows)
- SSH access to Unraid server (configured in scripts)
- Docker Compose on Unraid server

## Configuration

Edit the scripts to change:
- `UNRAID_HOST`: SSH host (default: `root@172.16.101.20`)
- `UNRAID_PATH`: Path on Unraid server (default: `/mnt/user/appdata/AgInfo`)

