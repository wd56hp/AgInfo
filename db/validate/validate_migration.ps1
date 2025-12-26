# Migration Validation Script (PowerShell)
# Runs pre-migration checks, applies migration, then post-migration checks

param(
    [Parameter(Mandatory=$true)]
    [string]$MigrationFile,
    
    [string]$DbHost = "172.16.101.20",
    [int]$DbPort = 15433,
    [string]$DbName = "aginfo",
    [string]$DbUser = "agadmin",
    [string]$ContainerName = "aginfo-postgis"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Migration Validation Process" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Database: $DbName @ ${DbHost}:${DbPort}"
Write-Host "Migration file: $MigrationFile"
Write-Host ""

if (-not (Test-Path $MigrationFile)) {
    Write-Host "Error: Migration file not found: $MigrationFile" -ForegroundColor Red
    exit 1
}

# Step 1: Run pre-migration checks
Write-Host "Step 1: Running pre-migration checks..." -ForegroundColor Yellow
$preCheckResult = docker exec $ContainerName psql -U $DbUser -d $DbName -f /tmp/validate/01_pre_migration_checks.sql 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Pre-migration checks failed. Aborting migration." -ForegroundColor Red
    Write-Host $preCheckResult
    exit 1
}
Write-Host "✓ Pre-migration checks passed" -ForegroundColor Green
Write-Host ""

# Step 2: Backup database
Write-Host "Step 2: Creating backup..." -ForegroundColor Yellow
$backupFile = "backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"
docker exec $ContainerName pg_dump -U $DbUser -d $DbName | Out-File -FilePath $backupFile -Encoding utf8
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Backup created: $backupFile" -ForegroundColor Green
} else {
    Write-Host "WARNING: Backup failed, but continuing..." -ForegroundColor Yellow
}
Write-Host ""

# Step 3: Apply migration
Write-Host "Step 3: Applying migration..." -ForegroundColor Yellow
Get-Content $MigrationFile | docker exec -i $ContainerName psql -U $DbUser -d $DbName
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Migration failed. Database may be in inconsistent state." -ForegroundColor Red
    Write-Host "Consider restoring from backup: $backupFile" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Migration applied successfully" -ForegroundColor Green
Write-Host ""

# Step 4: Run post-migration checks
Write-Host "Step 4: Running post-migration checks..." -ForegroundColor Yellow
$postCheckResult = docker exec $ContainerName psql -U $DbUser -d $DbName -f /tmp/validate/02_post_migration_checks.sql 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Post-migration checks failed. Review errors above." -ForegroundColor Red
    Write-Host $postCheckResult
    exit 1
}
Write-Host "✓ Post-migration checks passed" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Migration completed successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

