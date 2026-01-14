# AgInfo Backup Script (PowerShell)
# Creates a complete backup of database and application data

param(
    [string]$BackupDir = "",
    [switch]$Compress = $false,
    [switch]$SkipGeoServer = $false,
    [switch]$SkipWeb = $false
)

$ErrorActionPreference = "Stop"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Setup logging
$LogDir = Join-Path $ScriptDir "logs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "backup_$Timestamp.log"

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

# Load .env file if it exists (from project root)
$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path $envPath) {
    Write-Log "Loading environment variables from .env file"
    Get-Content $envPath | ForEach-Object {
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
$BackupTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupPath = Join-Path $BackupDir "aginfo_backup_$BackupTimestamp"

Write-Log "========================================"
Write-Log "AgInfo Backup Script"
Write-Log "========================================"
Write-Log "Backup Directory: $BackupPath"
Write-Log "Log File: $LogFile"
Write-Log ""

# Create backup directory structure
Write-Log "Creating backup directory structure..."
New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "database") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "geoserver") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "web") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "django") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BackupPath "config") -Force | Out-Null
Write-Log "Backup directories created"

# Check if Docker containers are running
Write-Log "Checking Docker containers..." "INFO"
$postgisRunning = docker ps --filter "name=aginfo-postgis" --format "{{.Names}}" | Select-String -Pattern "aginfo-postgis"
$geoserverRunning = docker ps --filter "name=aginfo-geoserver" --format "{{.Names}}" | Select-String -Pattern "aginfo-geoserver"

if (-not $postgisRunning) {
    Write-Log "WARNING: PostGIS container is not running. Database backup may fail." "WARN"
}

# Backup Database
Write-Log ""
Write-Log "Backing up PostgreSQL database..." "INFO"
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
    $dumpFile = Join-Path $BackupPath "database" "aginfo_backup.dump"
    
    Write-Log "  Exporting database to: $dumpFile" "INFO"
    $dumpOutput = docker exec aginfo-postgis pg_dump -U $dbUser -d $dbName -F c -f /tmp/aginfo_backup.dump 2>&1
    if ($dumpOutput) {
        Write-Log "  pg_dump output: $dumpOutput" "DEBUG"
    }
    
    if ($LASTEXITCODE -eq 0) {
        docker cp aginfo-postgis:/tmp/aginfo_backup.dump $dumpFile
        docker exec aginfo-postgis rm /tmp/aginfo_backup.dump
        
        $dumpSize = (Get-Item $dumpFile).Length / 1MB
        Write-Log "  ✓ Database backup complete ($([math]::Round($dumpSize, 2)) MB)" "INFO"
    } else {
        Write-Log "  ✗ Database backup failed (exit code: $LASTEXITCODE)" "ERROR"
        throw "Database backup failed"
    }
} catch {
    Write-Log "  ✗ Error backing up database: $_" "ERROR"
    Write-Log "  Stack trace: $($_.ScriptStackTrace)" "ERROR"
    Write-Log "  Continuing with other backups..." "WARN"
}

# Backup GeoServer data
if (-not $SkipGeoServer) {
    Write-Log ""
    Write-Log "Backing up GeoServer data..." "INFO"
    try {
        $geoserverSource = Join-Path $ProjectRoot "geoserver\data_dir"
        $geoserverDest = Join-Path $BackupPath "geoserver\data_dir"
        
        if (Test-Path $geoserverSource) {
            Write-Log "  Copying GeoServer data directory..." "INFO"
            Copy-Item -Path $geoserverSource -Destination $geoserverDest -Recurse -Force
            
            $geoserverSize = (Get-ChildItem $geoserverDest -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
            Write-Log "  ✓ GeoServer backup complete ($([math]::Round($geoserverSize, 2)) MB)" "INFO"
        } else {
            Write-Log "  ⚠ GeoServer data directory not found, skipping..." "WARN"
        }
    } catch {
        Write-Log "  ✗ Error backing up GeoServer: $_" "ERROR"
    }
} else {
    Write-Log ""
    Write-Log "Skipping GeoServer backup (--SkipGeoServer flag)" "INFO"
}

# Backup Web files
if (-not $SkipWeb) {
    Write-Log ""
    Write-Log "Backing up web files..." "INFO"
    try {
        $webSource = Join-Path $ProjectRoot "web"
        $webDest = Join-Path $BackupPath "web"
        
        if (Test-Path $webSource) {
            Write-Log "  Copying web directory..." "INFO"
            Copy-Item -Path $webSource -Destination $webDest -Recurse -Force
            
            $webSize = (Get-ChildItem $webDest -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
            Write-Log "  ✓ Web files backup complete ($([math]::Round($webSize, 2)) MB)" "INFO"
        } else {
            Write-Log "  ⚠ Web directory not found, skipping..." "WARN"
        }
    } catch {
        Write-Log "  ✗ Error backing up web files: $_" "ERROR"
    }
} else {
    Write-Log ""
    Write-Log "Skipping web files backup (--SkipWeb flag)" "INFO"
}

# Backup Django static and media files
Write-Log ""
Write-Log "Backing up Django files..." "INFO"
try {
    $djangoStatic = Join-Path $ProjectRoot "aginfo_django\staticfiles"
    $djangoMedia = Join-Path $ProjectRoot "aginfo_django\media"
    $djangoDest = Join-Path $BackupPath "django"
    
    if (Test-Path $djangoStatic) {
        Write-Log "  Copying Django static files..." "INFO"
        Copy-Item -Path $djangoStatic -Destination (Join-Path $djangoDest "staticfiles") -Recurse -Force
    }
    
    if (Test-Path $djangoMedia) {
        Write-Log "  Copying Django media files..." "INFO"
        Copy-Item -Path $djangoMedia -Destination (Join-Path $djangoDest "media") -Recurse -Force
    }
    
    if ((Test-Path $djangoStatic) -or (Test-Path $djangoMedia)) {
        Write-Log "  ✓ Django files backup complete" "INFO"
    } else {
        Write-Log "  ⚠ Django static/media directories not found, skipping..." "WARN"
    }
} catch {
    Write-Log "  ✗ Error backing up Django files: $_" "ERROR"
}

# Backup configuration files
Write-Log ""
Write-Log "Backing up configuration files..." "INFO"
try {
    $configDest = Join-Path $BackupPath "config"
    
    # Backup .env files (if they exist)
    if (Test-Path $envPath) {
        Copy-Item -Path $envPath -Destination (Join-Path $configDest ".env") -Force
        Write-Log "  ✓ .env file backed up" "INFO"
    }
    
    # Backup docker-compose.yml
    $dockerComposePath = Join-Path $ProjectRoot "docker-compose.yml"
    if (Test-Path $dockerComposePath) {
        Copy-Item -Path $dockerComposePath -Destination (Join-Path $configDest "docker-compose.yml") -Force
    }
    
    # Backup Django settings (for reference)
    $settingsPath = Join-Path $ProjectRoot "aginfo_django\settings.py"
    if (Test-Path $settingsPath) {
        Copy-Item -Path $settingsPath -Destination (Join-Path $configDest "settings.py") -Force
    }
    
    Write-Log "  ✓ Configuration files backed up" "INFO"
} catch {
    Write-Log "  ✗ Error backing up configuration: $_" "ERROR"
}

# Create backup manifest
Write-Log ""
Write-Log "Creating backup manifest..." "INFO"
$manifest = @{
    timestamp = $BackupTimestamp
    date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    backup_path = $BackupPath
    log_file = $LogFile
    database = @{
        name = $dbName
        user = $dbUser
        host = $dbHost
        backup_file = "database\aginfo_backup.dump"
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
Write-Log "  ✓ Manifest created" "INFO"

# Compress backup if requested
if ($Compress) {
    Write-Log ""
    Write-Log "Compressing backup..." "INFO"
    try {
        $zipFile = "$BackupPath.zip"
        Compress-Archive -Path $BackupPath -DestinationPath $zipFile -Force
        
        $zipSize = (Get-Item $zipFile).Length / 1MB
        Write-Log "  ✓ Backup compressed ($([math]::Round($zipSize, 2)) MB)" "INFO"
        
        # Optionally remove uncompressed backup
        Write-Log "  Removing uncompressed backup..." "INFO"
        Remove-Item -Path $BackupPath -Recurse -Force
        Write-Log "  ✓ Compression complete" "INFO"
    } catch {
        Write-Log "  ✗ Error compressing backup: $_" "ERROR"
    }
}

# Summary
Write-Log ""
Write-Log "========================================"
Write-Log "Backup Complete!" "INFO"
Write-Log "========================================"
Write-Log "Backup location: $BackupPath" "INFO"
Write-Log "Log file: $LogFile" "INFO"
if ($Compress) {
    Write-Log "Compressed file: $BackupPath.zip" "INFO"
}
Write-Log ""
Write-Log "To restore this backup, use:" "INFO"
Write-Log "  .\backup\restore.ps1 -BackupPath `"$BackupPath`"" "INFO"
Write-Log ""
