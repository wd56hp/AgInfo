# PowerShell script to import SQL files from db/temp directory into PostgreSQL database
# Usage: .\import_data.ps1 [pattern]
# Example: .\import_data.ps1 "011*" to import files matching 011*

param(
    [string]$Pattern = "*.sql",
    [string]$DbHost = $env:POSTGRES_HOST ?? "localhost",
    [int]$DbPort = $env:POSTGRES_PORT ?? 15433,
    [string]$DbName = $env:POSTGRES_DB ?? "aginfo",
    [string]$DbUser = $env:POSTGRES_USER ?? "agadmin",
    [string]$DbPassword = $env:POSTGRES_PASSWORD ?? "changeme",
    [string]$TempDir = $env:TEMP_DIR ?? ".\db\temp"
)

Write-Host "AgInfo Data Import Script" -ForegroundColor Green
Write-Host "=================================="
Write-Host "Database: ${DbName}@${DbHost}:${DbPort}"
Write-Host "User: ${DbUser}"
Write-Host "Pattern: ${Pattern}"
Write-Host "Temp directory: ${TempDir}"
Write-Host ""

# Check if temp directory exists
if (-not (Test-Path $TempDir)) {
    Write-Host "Error: Temp directory not found: ${TempDir}" -ForegroundColor Red
    exit 1
}

# Find files matching the pattern
$files = Get-ChildItem -Path $TempDir -Filter $Pattern -File | Sort-Object Name

if ($files.Count -eq 0) {
    Write-Host "Warning: No files found matching pattern: ${Pattern}" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($files.Count) file(s) to import" -ForegroundColor Green
Write-Host ""

# Import each file
$successCount = 0
$failCount = 0
$failedFiles = @()

foreach ($file in $files) {
    Write-Host "Importing: $($file.Name)..." -ForegroundColor Yellow
    
    # Build psql command
    $env:PGPASSWORD = $DbPassword
    $psqlArgs = @(
        "-h", $DbHost
        "-p", $DbPort
        "-U", $DbUser
        "-d", $DbName
        "-f", $file.FullName
    )
    
    try {
        $result = & psql $psqlArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Successfully imported: $($file.Name)" -ForegroundColor Green
            $successCount++
        } else {
            Write-Host "  ✗ Failed to import: $($file.Name)" -ForegroundColor Red
            Write-Host "    Error: $result" -ForegroundColor Red
            $failCount++
            $failedFiles += $file.Name
        }
    } catch {
        Write-Host "  ✗ Failed to import: $($file.Name)" -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Red
        $failCount++
        $failedFiles += $file.Name
    }
}

# Summary
Write-Host ""
Write-Host "=================================="
Write-Host "Import Summary:" -ForegroundColor Green
Write-Host "  Success: $successCount"
Write-Host "  Failed:  $failCount"

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Failed files:" -ForegroundColor Red
    foreach ($failedFile in $failedFiles) {
        Write-Host "  - $failedFile"
    }
    exit 1
}

Write-Host "All files imported successfully!" -ForegroundColor Green
exit 0

