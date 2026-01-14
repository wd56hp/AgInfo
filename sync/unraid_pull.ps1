# Pull ignored/local-only files from Unraid server to local workstation
# PowerShell version - uses WSL for rsync/ssh operations
# Works from: PowerShell, Windows CMD

$UNRAID_HOST = "root@172.16.101.20"
$UNRAID_PATH = "/mnt/user/appdata/AgInfo"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Pulling ignored files from Unraid server" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Host: $UNRAID_HOST"
Write-Host "Path: $UNRAID_PATH"
Write-Host "Using: WSL for rsync/ssh operations"
Write-Host ""

Write-Host "[1/3] Verifying WSL and rsync..." -ForegroundColor Yellow
$wslCheck = wsl bash -c "which rsync >/dev/null 2>&1 && echo 'OK' || echo 'FAIL'"
if ($wslCheck -ne "OK") {
    Write-Host "✗ ERROR: rsync not available in WSL" -ForegroundColor Red
    Write-Host "Ensure WSL is installed and rsync exists in your distro." -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] rsync available in WSL" -ForegroundColor Green
Write-Host ""

Write-Host "[2/3] Testing SSH connection (non-interactive)..." -ForegroundColor Yellow
$sshTest = wsl bash -c "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@172.16.101.20 'echo OK' 2>&1"
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] SSH connection successful" -ForegroundColor Green
} else {
    Write-Host "[FAIL] SSH connection failed" -ForegroundColor Red
    Write-Host "Most common causes:" -ForegroundColor Yellow
    Write-Host "  - SSH key not set up for root@172.16.101.20"
    Write-Host "  - Host unreachable / firewall"
    Write-Host "Fix (inside WSL):" -ForegroundColor Yellow
    Write-Host "  ssh-keygen -t ed25519"
    Write-Host "  ssh-copy-id $UNRAID_HOST"
    Write-Host ""
    Write-Host "Aborting to avoid hanging on prompts." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""

Write-Host "[3/3] Pulling .env file..." -ForegroundColor Yellow
$pullResult = wsl bash -c "rsync -avz -e 'ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5' `"${UNRAID_HOST}:${UNRAID_PATH}/.env`" ./.env 2>&1"
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] .env pulled successfully" -ForegroundColor Green
} else {
    Write-Host "[WARN] .env not found on server or pull failed (this is OK if file doesn't exist)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "[OK] Pull complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: db/data and geoserver/data_dir are not pulled as they are large and gitignored." -ForegroundColor Yellow
Write-Host "If you need them, uncomment the relevant lines in unraid_pull.sh" -ForegroundColor Yellow
