# Sync local code to Unraid server for testing without committing
# PowerShell version - delegates to bash script via WSL
# Works from: PowerShell, Windows CMD
# Avoids "hangs" by forcing non-interactive SSH (fails fast if auth isn't set up)

$UNRAID_HOST = "root@172.16.101.20"
$UNRAID_PATH = "/mnt/user/appdata/AgInfo"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Syncing local code to Unraid server" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Host: $UNRAID_HOST"
Write-Host "Path: $UNRAID_PATH"
Write-Host "Using: WSL to run bash sync script"
Write-Host ""

# Get the script directory and convert to WSL path
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$currentDir = (Get-Location).Path
$wslCurrentDir = $currentDir -replace '^([A-Z]):', '/mnt/$1' -replace '\\', '/'
$wslCurrentDir = $wslCurrentDir.ToLower()
$wslScriptPath = "$wslCurrentDir/sync/unraid_sync.sh"

Write-Host "[INFO] Running bash sync script via WSL..." -ForegroundColor Yellow
Write-Host ""

# Run the bash script via WSL
wsl bash "$wslScriptPath"
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "[OK] Sync complete via bash script!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[FAIL] Sync failed with exit code: $exitCode" -ForegroundColor Red
}

exit $exitCode
