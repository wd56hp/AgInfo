# AgInfo Backup and Restore Guide

This guide explains how to backup and restore your AgInfo application data, including the database, GeoServer configuration, web files, and Django static/media files.

## Overview

The backup system creates complete backups of:
- **PostgreSQL/PostGIS Database**: Full database dump using `pg_dump`
- **GeoServer Data**: Complete GeoServer data directory
- **Web Files**: All web application files
- **Django Files**: Static files and media uploads
- **Configuration**: Environment files and key configuration files

## Prerequisites

- Docker and Docker Compose must be installed
- The AgInfo containers should be running (at least the PostGIS container for database backup)
- For PowerShell scripts: Windows with PowerShell 5.1+ or PowerShell Core
- For Bash scripts: Linux/Unix/macOS or Git Bash on Windows

## Logging

All backup and restore operations are logged to timestamped log files in the `backup/logs/` directory:
- Backup logs: `backup/logs/backup_YYYYMMDD_HHMMSS.log`
- Restore logs: `backup/logs/restore_YYYYMMDD_HHMMSS.log`

Logs include timestamps, log levels (INFO, WARN, ERROR, DEBUG), and detailed operation information for troubleshooting.

## Configuration

The backup location can be configured via environment variable. Create a `.env` file (copy from `.env.example`) and set:

```bash
BACKUP_DIR=backups
```

Or use an absolute path:

```bash
BACKUP_DIR=/path/to/backups
# Windows
BACKUP_DIR=C:\Backups\AgInfo
```

If not set, backups will default to the `backups` directory in the project root.

## Backup Scripts

### PowerShell (Windows)

```powershell
# Basic backup (uses BACKUP_DIR from .env or defaults to "backups")
.\backup\backup.ps1

# Backup with compression
.\backup\backup.ps1 -Compress

# Override backup directory (takes precedence over .env)
.\backup\backup.ps1 -BackupDir "C:\Backups\AgInfo"

# Skip GeoServer or Web files (faster backups)
.\backup\backup.ps1 -SkipGeoServer
.\backup\backup.ps1 -SkipWeb
```

### Bash (Linux/Unix/macOS)

```bash
# Make script executable (first time only)
chmod +x backup/backup.sh

# Basic backup (uses BACKUP_DIR from .env or defaults to "backups")
./backup/backup.sh

# Backup with compression
./backup/backup.sh --compress

# Override backup directory (takes precedence over .env)
./backup/backup.sh --backup-dir /backups/aginfo

# Skip GeoServer or Web files
./backup/backup.sh --skip-geoserver
./backup/backup.sh --skip-web
```

## Restore Scripts

### PowerShell (Windows)

```powershell
# Restore from backup
.\backup\restore.ps1 -BackupPath "backups\aginfo_backup_20240101_120000"

# Restore with force (skip confirmation)
.\backup\restore.ps1 -BackupPath "backups\aginfo_backup_20240101_120000" -Force

# Restore specific components only
.\backup\restore.ps1 -BackupPath "backups\aginfo_backup_20240101_120000" -SkipGeoServer
.\backup\restore.ps1 -BackupPath "backups\aginfo_backup_20240101_120000" -SkipWeb
.\backup\restore.ps1 -BackupPath "backups\aginfo_backup_20240101_120000" -SkipDatabase
```

### Bash (Linux/Unix/macOS)

```bash
# Make script executable (first time only)
chmod +x backup/restore.sh

# Restore from backup
./backup/restore.sh --backup-path "backups/aginfo_backup_20240101_120000"

# Restore with force (skip confirmation)
./backup/restore.sh --backup-path "backups/aginfo_backup_20240101_120000" --force

# Restore specific components only
./backup/restore.sh --backup-path "backups/aginfo_backup_20240101_120000" --skip-geoserver
./backup/restore.sh --backup-path "backups/aginfo_backup_20240101_120000" --skip-web
./backup/restore.sh --backup-path "backups/aginfo_backup_20240101_120000" --skip-database
```

## Backup Structure

Each backup creates a directory with the following structure:

```
aginfo_backup_YYYYMMDD_HHMMSS/
├── manifest.json          # Backup metadata and information
├── database/
│   └── aginfo_backup.dump # PostgreSQL database dump
├── geoserver/
│   └── data_dir/          # GeoServer configuration and data
├── web/                   # Web application files
├── django/
│   ├── staticfiles/       # Django static files
│   └── media/             # Django media uploads
└── config/
    ├── .env               # Environment variables (if exists)
    ├── docker-compose.yml # Docker Compose configuration
    └── settings.py        # Django settings (for reference)
```

## Backup Process

1. **Database Backup**: Uses `pg_dump` to create a PostgreSQL custom format dump
2. **GeoServer Backup**: Copies the entire GeoServer data directory
3. **Web Files Backup**: Copies all web application files
4. **Django Files Backup**: Copies static files and media uploads
5. **Configuration Backup**: Copies environment and configuration files
6. **Manifest Creation**: Creates a JSON manifest with backup metadata

## Restore Process

1. **Verification**: Checks backup path and manifest
2. **Confirmation**: Prompts for confirmation (unless `--force` is used)
3. **Database Restore**: Drops and recreates database, then restores from dump
4. **File Restore**: Restores GeoServer, web, and Django files
5. **Configuration Review**: Provides location of backed up config files for manual review

## Important Notes

### Database Restore

- **WARNING**: Database restore will **DROP** the existing database and recreate it
- All existing data will be lost
- Make sure you have a current backup before restoring
- The PostGIS container must be running for database restore

### Configuration Files

- `.env` files are backed up but **NOT automatically restored** for safety
- Review and manually restore configuration files if needed
- Never restore `.env` files without reviewing changes first

### Container Restart

After restoring, you should restart the containers:

```bash
docker-compose restart
```

Or restart specific services:

```bash
docker-compose restart postgis
docker-compose restart geoserver
docker-compose restart django
```

## Automated Backups

### Windows Task Scheduler

You can schedule regular backups using Windows Task Scheduler:

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily, weekly, etc.)
4. Action: Start a program
5. Program: `powershell.exe`
6. Arguments: `-File "C:\path\to\AgInfo\backup\backup.ps1" -Compress`

### Linux Cron

Add to crontab for daily backups at 2 AM:

```bash
0 2 * * * /path/to/AgInfo/backup/backup.sh --compress >> /var/log/aginfo-backup.log 2>&1
```

### Backup Retention

Consider implementing backup rotation to avoid filling disk space:

```powershell
# PowerShell: Keep only last 7 backups
Get-ChildItem backups\aginfo_backup_* | Sort-Object CreationTime -Descending | Select-Object -Skip 7 | Remove-Item -Recurse -Force
```

```bash
# Bash: Keep only last 7 backups
ls -t backups/aginfo_backup_* | tail -n +8 | xargs rm -rf
```

## Troubleshooting

### Database Backup Fails

- Ensure the PostGIS container is running: `docker ps | grep aginfo-postgis`
- Check database credentials in environment variables
- Verify database connection: `docker exec aginfo-postgis pg_isready -U agadmin`

### Permission Errors

- Ensure you have write permissions to the backup directory
- On Linux, you may need `sudo` for some operations
- Check Docker container permissions

### Restore Fails

- Ensure containers are running before restore
- Check that backup files are not corrupted
- Verify disk space is available
- Review error messages for specific issues

### Large Backups

- Use `--compress` to reduce backup size
- Consider excluding GeoServer cache: `--skip-geoserver` (if cache can be regenerated)
- Use `--skip-web` if web files are in version control

## Best Practices

1. **Regular Backups**: Schedule automated daily backups
2. **Test Restores**: Periodically test restore process to ensure backups work
3. **Offsite Storage**: Copy backups to remote location or cloud storage
4. **Backup Before Updates**: Always backup before major updates or migrations
5. **Document Changes**: Note any configuration changes between backups
6. **Monitor Disk Space**: Ensure adequate space for backups
7. **Encryption**: Consider encrypting backups if they contain sensitive data

## Backup Verification

After creating a backup, verify it:

1. Check that `manifest.json` exists and is valid
2. Verify database dump file exists and has reasonable size
3. Check that all expected directories are present
4. Test restore on a test environment if possible

## Support

For issues or questions:
- Check the manifest.json in the backup for details
- Review Docker container logs: `docker-compose logs`
- Verify environment variables are set correctly
- Check file permissions and disk space

