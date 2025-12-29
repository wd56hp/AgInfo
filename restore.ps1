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

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AgInfo Restore Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backup Path: $BackupPath" -ForegroundColor Yellow
Write-Host ""

# Check if backup path exists
if (-not (Test-Path $BackupPath)) {
    # Try with .zip extension
    if (Test-Path "$BackupPath.zip") {
        Write-Host "Found compressed backup, extracting..." -ForegroundColor Yellow
        $ExtractPath = $BackupPath
        Expand-Archive -Path "$BackupPath.zip" -DestinationPath (Split-Path $BackupPath) -Force
        Write-Host "✓ Extraction complete" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Backup path not found: $BackupPath" -ForegroundColor Red
        exit 1
    }
}

# Check for manifest
$manifestPath = Join-Path $BackupPath "manifest.json"
if (-not (Test-Path $manifestPath)) {
    Write-Host "WARNING: Manifest file not found. Proceeding with restore anyway..." -ForegroundColor Yellow
} else {
    $manifest = Get-Content $manifestPath | ConvertFrom-Json
    Write-Host "Backup Information:" -ForegroundColor Cyan
    Write-Host "  Date: $($manifest.date)" -ForegroundColor Gray
    Write-Host "  Timestamp: $($manifest.timestamp)" -ForegroundColor Gray
    Write-Host ""
}

# Confirm restore
if (-not $Force) {
    Write-Host "WARNING: This will overwrite existing data!" -ForegroundColor Red
    $confirm = Read-Host "Type 'yes' to continue"
    if ($confirm -ne "yes") {
        Write-Host "Restore cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# Restore Database
if (-not $SkipDatabase) {
    Write-Host ""
    Write-Host "Restoring PostgreSQL database..." -ForegroundColor Green
    
    # Check if container is running
    $postgisRunning = docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | Select-String -Pattern "aginfo-postgis"
    if (-not $postgisRunning) {
        Write-Host "ERROR: PostGIS container is not running. Please start it first." -ForegroundColor Red
        Write-Host "  Run: docker-compose up -d postgis" -ForegroundColor Yellow
        exit 1
    }
    
    try {
        $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.sql"
        if (-not (Test-Path $dumpFile)) {
            $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.dump"
        }
        
        if (-not (Test-Path $dumpFile)) {
            Write-Host "  ✗ Database backup file not found: $dumpFile" -ForegroundColor Red
        } else {
            # Get database credentials
            $dbName = $env:POSTGRES_DB
            if (-not $dbName) { $dbName = "aginfo" }
            
            $dbUser = $env:POSTGRES_USER
            if (-not $dbUser) { $dbUser = "agadmin" }
            
            Write-Host "  Copying dump file to container..." -ForegroundColor Gray
            docker cp $dumpFile aginfo-postgis:/tmp/aginfo_restore.dump
            
            Write-Host "  Dropping existing database connections..." -ForegroundColor Gray
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$dbName' AND pid <> pg_backend_pid();" 2>&1 | Out-Null
            
            Write-Host "  Dropping and recreating database..." -ForegroundColor Gray
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "DROP DATABASE IF EXISTS $dbName;" 2>&1 | Out-Null
            docker exec aginfo-postgis psql -U $dbUser -d postgres -c "CREATE DATABASE $dbName;" 2>&1 | Out-Null
            
            Write-Host "  Restoring database from backup..." -ForegroundColor Gray
            docker exec aginfo-postgis pg_restore -U $dbUser -d $dbName -F c /tmp/aginfo_restore.dump 2>&1 | Out-Null
            
            if ($LASTEXITCODE -eq 0) {
                docker exec aginfo-postgis rm /tmp/aginfo_restore.dump
                Write-Host "  ✓ Database restore complete" -ForegroundColor Green
            } else {
                Write-Host "  ✗ Database restore failed" -ForegroundColor Red
                throw "Database restore failed"
            }
        }
    } catch {
        Write-Host "  ✗ Error restoring database: $_" -ForegroundColor Red
        Write-Host "  Continuing with other restores..." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Skipping database restore (--SkipDatabase flag)" -ForegroundColor Yellow
}

# Restore GeoServer data
if (-not $SkipGeoServer) {
    Write-Host ""
    Write-Host "Restoring GeoServer data..." -ForegroundColor Green
    try {
        $geoserverBackup = Join-Path $BackupPath "geoserver" "data_dir"
        $geoserverDest = "geoserver\data_dir"
        
        if (Test-Path $geoserverBackup) {
            Write-Host "  Restoring GeoServer data directory..." -ForegroundColor Gray
            if (Test-Path $geoserverDest) {
                Remove-Item -Path $geoserverDest -Recurse -Force
            }
            Copy-Item -Path $geoserverBackup -Destination $geoserverDest -Recurse -Force
            Write-Host "  ✓ GeoServer data restore complete" -ForegroundColor Green
            Write-Host "  NOTE: You may need to restart the GeoServer container" -ForegroundColor Yellow
        } else {
            Write-Host "  ⚠ GeoServer backup not found, skipping..." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ✗ Error restoring GeoServer data: $_" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "Skipping GeoServer restore (--SkipGeoServer flag)" -ForegroundColor Yellow
}

# Restore Web files
if (-not $SkipWeb) {
    Write-Host ""
    Write-Host "Restoring web files..." -ForegroundColor Green
    try {
        $webBackup = Join-Path $BackupPath "web"
        $webDest = "web"
        
        if (Test-Path $webBackup) {
            Write-Host "  Restoring web directory..." -ForegroundColor Gray
            if (Test-Path $webDest) {
                Remove-Item -Path $webDest -Recurse -Force
            }
            Copy-Item -Path $webBackup -Destination $webDest -Recurse -Force
            Write-Host "  ✓ Web files restore complete" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ Web backup not found, skipping..." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ✗ Error restoring web files: $_" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "Skipping web files restore (--SkipWeb flag)" -ForegroundColor Yellow
}

# Restore Django static and media files
Write-Host ""
Write-Host "Restoring Django files..." -ForegroundColor Green
try {
    $djangoBackup = Join-Path $BackupPath "django"
    $djangoStaticDest = "aginfo_django\staticfiles"
    $djangoMediaDest = "aginfo_django\media"
    
    if (Test-Path (Join-Path $djangoBackup "staticfiles")) {
        Write-Host "  Restoring Django static files..." -ForegroundColor Gray
        if (Test-Path $djangoStaticDest) {
            Remove-Item -Path $djangoStaticDest -Recurse -Force
        }
        Copy-Item -Path (Join-Path $djangoBackup "staticfiles") -Destination $djangoStaticDest -Recurse -Force
    }
    
    if (Test-Path (Join-Path $djangoBackup "media")) {
        Write-Host "  Restoring Django media files..." -ForegroundColor Gray
        if (Test-Path $djangoMediaDest) {
            Remove-Item -Path $djangoMediaDest -Recurse -Force
        }
        Copy-Item -Path (Join-Path $djangoBackup "media") -Destination $djangoMediaDest -Recurse -Force
    }
    
    if ((Test-Path (Join-Path $djangoBackup "staticfiles")) -or (Test-Path (Join-Path $djangoBackup "media"))) {
        Write-Host "  ✓ Django files restore complete" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Django backup not found, skipping..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ Error restoring Django files: $_" -ForegroundColor Red
}

# Restore configuration files (optional, with warning)
Write-Host ""
Write-Host "Configuration files restore..." -ForegroundColor Green
$configBackup = Join-Path $BackupPath "config"
if (Test-Path $configBackup) {
    Write-Host "  Configuration files are available in: $configBackup" -ForegroundColor Gray
    Write-Host "  Review and manually restore .env and other config files if needed" -ForegroundColor Yellow
    Write-Host "  WARNING: Do not overwrite .env without reviewing changes!" -ForegroundColor Red
} else {
    Write-Host "  ⚠ Configuration backup not found" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Restore Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review restored configuration files if needed" -ForegroundColor White
Write-Host "  2. Restart containers: docker-compose restart" -ForegroundColor White
Write-Host "  3. Verify the application is working correctly" -ForegroundColor White
Write-Host ""

