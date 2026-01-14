# AgInfo Restore Script (PowerShell)
# Restores a backup of database and application data

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupPath,
    [switch]$SkipGeoServer = $false,
    [switch]$SkipWeb = $false,
    [switch]$SkipDatabase = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Setup logging
$LogDir = Join-Path $ScriptDir "logs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "restore_$Timestamp.log"

# Create logs directory if it doesn't exist
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# Logging function
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $LogMessage = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Message"
    Add-Content -Path $LogFile -Value $LogMessage
    Write-Host $Message
}

Write-Log "========================================"
Write-Log "AgInfo Restore Script"
Write-Log "========================================"
Write-Log "Backup Path: $BackupPath"
Write-Log "Log File: $LogFile"
Write-Log ""

# Check if backup path exists
if (-not (Test-Path $BackupPath)) {
    # Try with .zip extension
    if (Test-Path "$BackupPath.zip") {
        Write-Log "Found compressed backup, extracting..." "INFO"
        $ExtractPath = $BackupPath
        Expand-Archive -Path "$BackupPath.zip" -DestinationPath (Split-Path $BackupPath) -Force
        Write-Log "✓ Extraction complete" "INFO"
    } else {
        Write-Log "ERROR: Backup path not found: $BackupPath" "ERROR"
        exit 1
    }
}

# Check for manifest
$manifestPath = Join-Path $BackupPath "manifest.json"
if (-not (Test-Path $manifestPath)) {
    Write-Log "WARNING: Manifest file not found. Proceeding with restore anyway..." "WARN"
} else {
    $manifest = Get-Content $manifestPath | ConvertFrom-Json
    Write-Log "Backup Information:" "INFO"
    Write-Log "  Date: $($manifest.date)" "INFO"
    Write-Log "  Timestamp: $($manifest.timestamp)" "INFO"
    Write-Log ""
}

# Confirm restore
if (-not $Force) {
    Write-Log "WARNING: This will overwrite existing data!" "WARN"
    $confirm = Read-Host "Type 'yes' to continue"
    if ($confirm -ne "yes") {
        Write-Log "Restore cancelled." "INFO"
        exit 0
    }
}

# Restore Database
if (-not $SkipDatabase) {
    Write-Log ""
    Write-Log "Restoring PostgreSQL database..." "INFO"
    
    # Check if container is running
    $postgisRunning = docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | Select-String -Pattern "aginfo-postgis"
    if (-not $postgisRunning) {
        Write-Log "ERROR: PostGIS container is not running. Please start it first." "ERROR"
        Write-Log "  Run: docker-compose up -d postgis" "INFO"
        exit 1
    }
    
    try {
        $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.dump"
        if (-not (Test-Path $dumpFile)) {
            $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.sql"
        }
        
        if (-not (Test-Path $dumpFile)) {
            Write-Log "  ✗ Database backup file not found: $dumpFile" "ERROR"
        } else {
            # Get database credentials
            $dbName = $env:POSTGRES_DB
            if (-not $dbName) { $dbName = "aginfo" }
            
            $dbUser = $env:POSTGRES_USER
            if (-not $dbUser) { $dbUser = "agadmin" }
            
            Write-Log "  Copying dump file to container..." "INFO"
            docker cp $dumpFile aginfo-postgis:/tmp/aginfo_restore.dump
            
            Write-Log "  Dropping existing database connections..." "INFO"
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$dbName' AND pid <> pg_backend_pid();" 2>&1 | Out-Null
            
            Write-Log "  Dropping and recreating database..." "INFO"
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "DROP DATABASE IF EXISTS $dbName;" 2>&1 | Out-Null
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "CREATE DATABASE $dbName;" 2>&1 | Out-Null
            
            Write-Log "  Restoring database from backup..." "INFO"
            $restoreOutput = docker exec aginfo-postgis pg_restore -U $dbUser -d $dbName -F c /tmp/aginfo_restore.dump 2>&1
            if ($restoreOutput) {
                Write-Log "  pg_restore output: $restoreOutput" "DEBUG"
            }
            
            if ($LASTEXITCODE -eq 0) {
                docker exec aginfo-postgis rm /tmp/aginfo_restore.dump
                Write-Log "  ✓ Database restore complete" "INFO"
            } else {
                Write-Log "  ✗ Database restore failed (exit code: $LASTEXITCODE)" "ERROR"
                throw "Database restore failed"
            }
        }
    } catch {
        Write-Log "  ✗ Error restoring database: $_" "ERROR"
        Write-Log "  Stack trace: $($_.ScriptStackTrace)" "ERROR"
        Write-Log "  Continuing with other restores..." "WARN"
    }
} else {
    Write-Log ""
    Write-Log "Skipping database restore (--SkipDatabase flag)" "INFO"
}

# Restore GeoServer data
if (-not $SkipGeoServer) {
    Write-Log ""
    Write-Log "Restoring GeoServer data..." "INFO"
    try {
        $geoserverBackup = Join-Path $BackupPath "geoserver" "data_dir"
        $geoserverDest = Join-Path $ProjectRoot "geoserver\data_dir"
        
        if (Test-Path $geoserverBackup) {
            Write-Log "  Restoring GeoServer data directory..." "INFO"
            if (Test-Path $geoserverDest) {
                Remove-Item -Path $geoserverDest -Recurse -Force
            }
            Copy-Item -Path $geoserverBackup -Destination $geoserverDest -Recurse -Force
            Write-Log "  ✓ GeoServer data restore complete" "INFO"
            Write-Log "  NOTE: You may need to restart the GeoServer container" "WARN"
        } else {
            Write-Log "  ⚠ GeoServer backup not found, skipping..." "WARN"
        }
    } catch {
        Write-Log "  ✗ Error restoring GeoServer data: $_" "ERROR"
    }
} else {
    Write-Log ""
    Write-Log "Skipping GeoServer restore (--SkipGeoServer flag)" "INFO"
}

# Restore Web files
if (-not $SkipWeb) {
    Write-Log ""
    Write-Log "Restoring web files..." "INFO"
    try {
        $webBackup = Join-Path $BackupPath "web"
        $webDest = Join-Path $ProjectRoot "web"
        
        if (Test-Path $webBackup) {
            Write-Log "  Restoring web directory..." "INFO"
            if (Test-Path $webDest) {
                Remove-Item -Path $webDest -Recurse -Force
            }
            Copy-Item -Path $webBackup -Destination $webDest -Recurse -Force
            Write-Log "  ✓ Web files restore complete" "INFO"
        } else {
            Write-Log "  ⚠ Web backup not found, skipping..." "WARN"
        }
    } catch {
        Write-Log "  ✗ Error restoring web files: $_" "ERROR"
    }
} else {
    Write-Log ""
    Write-Log "Skipping web files restore (--SkipWeb flag)" "INFO"
}

# Restore Django static and media files
Write-Log ""
Write-Log "Restoring Django files..." "INFO"
try {
    $djangoBackup = Join-Path $BackupPath "django"
    $djangoStaticDest = Join-Path $ProjectRoot "aginfo_django\staticfiles"
    $djangoMediaDest = Join-Path $ProjectRoot "aginfo_django\media"
    
    if (Test-Path (Join-Path $djangoBackup "staticfiles")) {
        Write-Log "  Restoring Django static files..." "INFO"
        if (Test-Path $djangoStaticDest) {
            Remove-Item -Path $djangoStaticDest -Recurse -Force
        }
        Copy-Item -Path (Join-Path $djangoBackup "staticfiles") -Destination $djangoStaticDest -Recurse -Force
    }
    
    if (Test-Path (Join-Path $djangoBackup "media")) {
        Write-Log "  Restoring Django media files..." "INFO"
        if (Test-Path $djangoMediaDest) {
            Remove-Item -Path $djangoMediaDest -Recurse -Force
        }
        Copy-Item -Path (Join-Path $djangoBackup "media") -Destination $djangoMediaDest -Recurse -Force
    }
    
    if ((Test-Path (Join-Path $djangoBackup "staticfiles")) -or (Test-Path (Join-Path $djangoBackup "media"))) {
        Write-Log "  ✓ Django files restore complete" "INFO"
    } else {
        Write-Log "  ⚠ Django backup not found, skipping..." "WARN"
    }
} catch {
    Write-Log "  ✗ Error restoring Django files: $_" "ERROR"
}

# Restore configuration files (optional, with warning)
Write-Log ""
Write-Log "Configuration files restore..." "INFO"
$configBackup = Join-Path $BackupPath "config"
if (Test-Path $configBackup) {
    Write-Log "  Configuration files are available in: $configBackup" "INFO"
    Write-Log "  Review and manually restore .env and other config files if needed" "WARN"
    Write-Log "  WARNING: Do not overwrite .env without reviewing changes!" "WARN"
} else {
    Write-Log "  ⚠ Configuration backup not found" "WARN"
}

# Summary
Write-Log ""
Write-Log "========================================"
Write-Log "Restore Complete!" "INFO"
Write-Log "========================================"
Write-Log ""
Write-Log "Next steps:" "INFO"
Write-Log "  1. Review restored configuration files if needed" "INFO"
Write-Log "  2. Restart containers: docker-compose restart" "INFO"
Write-Log "  3. Verify the application is working correctly" "INFO"
Write-Log ""
