# AgInfo Backup Script (PowerShell)
# Creates a complete backup of database and application data

param(
    [string]$BackupDir = "",
    [switch]$Compress = $false,
    [switch]$SkipGeoServer = $false,
    [switch]$SkipWeb = $false
)

$ErrorActionPreference = "Stop"

# Load .env file if it exists
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Get backup directory from environment variable, parameter, or default
if ([string]::IsNullOrEmpty($BackupDir)) {
    $BackupDir = $env:BACKUP_DIR
    if ([string]::IsNullOrEmpty($BackupDir)) {
        $BackupDir = "backups"
    }
}

# Get timestamp for backup directory
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupPath = Join-Path $BackupDir "aginfo_backup_$Timestamp"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AgInfo Backup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backup Directory: $BackupPath" -ForegroundColor Yellow
Write-Host ""

# Create backup directory structure
New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "database") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "geoserver") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "web") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "django") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "config") -Force | Out-Null

# Check if Docker containers are running
Write-Host "Checking Docker containers..." -ForegroundColor Yellow
$postgisRunning = docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | Select-String -Pattern "aginfo-postgis"
$geoserverRunning = docker ps --filter "name=aginfo-geoserver" --format "{{.Names}}" | Select-String -Pattern "aginfo-geoserver"

if (-not $postgisRunning) {
    Write-Host "WARNING: PostGIS container is not running. Database backup may fail." -ForegroundColor Red
}

# Backup Database
Write-Host ""
Write-Host "Backing up PostgreSQL database..." -ForegroundColor Green
try {
    # Get database credentials from environment or use defaults
    $dbName = $env:POSTGRES_DB
    if (-not $dbName) { $dbName = "aginfo" }
    
    $dbUser = $env:POSTGRES_USER
    if (-not $dbUser) { $dbUser = "agadmin" }
    
    $dbPassword = $env:POSTGRES_PASSWORD
    if (-not $dbPassword) { $dbPassword = "changeme" }
    
    $dbHost = $env:POSTGIS_HOST_PORT
    if (-not $dbHost) { $dbHost = "localhost:15433" }
    
    # Export database using pg_dump from container
    $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.sql"
    
    Write-Host "  Exporting database to: $dumpFile" -ForegroundColor Gray
    docker exec aginfo-postgis pg_dump -U $dbUser -d $dbName -F c -f /tmp/aginfo_backup.dump 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        docker cp aginfo-postgis:/tmp/aginfo_backup.dump $dumpFile
        docker exec aginfo-postgis rm /tmp/aginfo_backup.dump
        
        $dumpSize = (Get-Item $dumpFile).Length / 1MB
        Write-Host "  ✓ Database backup complete ($([math]::Round($dumpSize, 2)) MB)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Database backup failed" -ForegroundColor Red
        throw "Database backup failed"
    }
} catch {
    Write-Host "  ✗ Error backing up database: $_" -ForegroundColor Red
    Write-Host "  Continuing with other backups..." -ForegroundColor Yellow
}

# Backup GeoServer data
if (-not $SkipGeoServer) {
    Write-Host ""
    Write-Host "Backing up GeoServer data..." -ForegroundColor Green
    try {
        $geoserverSource = "geoserver\data_dir"
        $geoserverDest = Join-Path $BackupPath "geoserver\data_dir"
        
        if (Test-Path $geoserverSource) {
            Write-Host "  Copying GeoServer data directory..." -ForegroundColor Gray
            Copy-Item -Path $geoserverSource -Destination $geoserverDest -Recurse -Force
            
            $geoserverSize = (Get-ChildItem $geoserverDest -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
            Write-Host "  ✓ GeoServer backup complete ($([math]::Round($geoserverSize, 2)) MB)" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ GeoServer data directory not found, skipping..." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ✗ Error backing up GeoServer: $_" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "Skipping GeoServer backup (--SkipGeoServer flag)" -ForegroundColor Yellow
}

# Backup Web files
if (-not $SkipWeb) {
    Write-Host ""
    Write-Host "Backing up web files..." -ForegroundColor Green
    try {
        $webSource = "web"
        $webDest = Join-Path $BackupPath "web"
        
        if (Test-Path $webSource) {
            Write-Host "  Copying web directory..." -ForegroundColor Gray
            Copy-Item -Path $webSource -Destination $webDest -Recurse -Force
            
            $webSize = (Get-ChildItem $webDest -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
            Write-Host "  ✓ Web files backup complete ($([math]::Round($webSize, 2)) MB)" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ Web directory not found, skipping..." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ✗ Error backing up web files: $_" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "Skipping web files backup (--SkipWeb flag)" -ForegroundColor Yellow
}

# Backup Django static and media files
Write-Host ""
Write-Host "Backing up Django files..." -ForegroundColor Green
try {
    $djangoStatic = "aginfo_django\staticfiles"
    $djangoMedia = "aginfo_django\media"
    $djangoDest = Join-Path $BackupPath "django"
    
    if (Test-Path $djangoStatic) {
        Write-Host "  Copying Django static files..." -ForegroundColor Gray
        Copy-Item -Path $djangoStatic -Destination (Join-Path $djangoDest "staticfiles") -Recurse -Force
    }
    
    if (Test-Path $djangoMedia) {
        Write-Host "  Copying Django media files..." -ForegroundColor Gray
        Copy-Item -Path $djangoMedia -Destination (Join-Path $djangoDest "media") -Recurse -Force
    }
    
    if ((Test-Path $djangoStatic) -or (Test-Path $djangoMedia)) {
        Write-Host "  ✓ Django files backup complete" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Django static/media directories not found, skipping..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ Error backing up Django files: $_" -ForegroundColor Red
}

# Backup configuration files
Write-Host ""
Write-Host "Backing up configuration files..." -ForegroundColor Green
try {
    $configDest = Join-Path $BackupPath "config"
    
    # Backup .env files (if they exist)
    if (Test-Path ".env") {
        Copy-Item -Path ".env" -Destination (Join-Path $configDest ".env") -Force
        Write-Host "  ✓ .env file backed up" -ForegroundColor Green
    }
    
    # Backup docker-compose.yml
    if (Test-Path "docker-compose.yml") {
        Copy-Item -Path "docker-compose.yml" -Destination (Join-Path $configDest "docker-compose.yml") -Force
    }
    
    # Backup Django settings (for reference)
    if (Test-Path "aginfo_django\settings.py") {
        Copy-Item -Path "aginfo_django\settings.py" -Destination (Join-Path $configDest "settings.py") -Force
    }
    
    Write-Host "  ✓ Configuration files backed up" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Error backing up configuration: $_" -ForegroundColor Red
}

# Create backup manifest
Write-Host ""
Write-Host "Creating backup manifest..." -ForegroundColor Green
$manifest = @{
    timestamp = $Timestamp
    date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    backup_path = $BackupPath
    database = @{
        name = $dbName
        user = $dbUser
        host = $dbHost
        backup_file = "database\aginfo_backup.sql"
    }
    components = @{
        database = $true
        geoserver = (-not $SkipGeoServer)
        web = (-not $SkipWeb)
        django = $true
        config = $true
    }
} | ConvertTo-Json -Depth 10

$manifest | Out-File -FilePath (Join-Path $BackupPath "manifest.json") -Encoding UTF8
Write-Host "  ✓ Manifest created" -ForegroundColor Green

# Compress backup if requested
if ($Compress) {
    Write-Host ""
    Write-Host "Compressing backup..." -ForegroundColor Green
    try {
        $zipFile = "$BackupPath.zip"
        Compress-Archive -Path $BackupPath -DestinationPath $zipFile -Force
        
        $zipSize = (Get-Item $zipFile).Length / 1MB
        Write-Host "  ✓ Backup compressed ($([math]::Round($zipSize, 2)) MB)" -ForegroundColor Green
        
        # Optionally remove uncompressed backup
        Write-Host "  Removing uncompressed backup..." -ForegroundColor Gray
        Remove-Item -Path $BackupPath -Recurse -Force
        Write-Host "  ✓ Compression complete" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Error compressing backup: $_" -ForegroundColor Red
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backup location: $BackupPath" -ForegroundColor Yellow
if ($Compress) {
    Write-Host "Compressed file: $BackupPath.zip" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "To restore this backup, use:" -ForegroundColor Cyan
Write-Host "  .\restore.ps1 -BackupPath `"$BackupPath`"" -ForegroundColor White
Write-Host ""

