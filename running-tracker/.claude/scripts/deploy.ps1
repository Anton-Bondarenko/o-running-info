# deploy.ps1 — Deploy running-tracker to Raspberry Pi (raspinas)
# Usage: .\deploy.ps1

param(
    [string]$Host = $env:DEPLOY_HOST ?? "raspinas",
    [string]$User = $env:DEPLOY_USER,
    [string]$Password = $env:DEPLOY_PASSWORD
)

if (-not $User -or -not $Password) {
    Write-Host "[deploy] ERROR: DEPLOY_USER and DEPLOY_PASSWORD must be set in .env" -ForegroundColor Red
    exit 1
}

$RemoteDir = "/home/$User/o-running-info/running-tracker"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[deploy] Target: ${User}@${Host}:${RemoteDir}" -ForegroundColor Cyan

# 1. Create remote directory (using plink instead of sshpass)
plink -pw $Password -P 22 ${User}@${Host} "mkdir -p ${RemoteDir}/data" >$null

# 2. rsync project files (skip .git, venv, __pycache__, test-screenshots)
Write-Host "[deploy] Syncing files..." -ForegroundColor Cyan
rsync -avz --delete `
    --exclude=".git/" `
    --exclude="venv/" `
    --exclude="__pycache__/" `
    --exclude="test-screenshots/" `
    --exclude="*.pyc" `
    --exclude=".pytest_cache/" `
    --exclude=".claude/" `
    ${RepoRoot}\ .\ `
    ${User}@${Host}:${RemoteDir}/

# 3. Deploy .env to remote
Write-Host "[deploy] Deploying .env..." -ForegroundColor Cyan
scp `
    -o StrictHostKeyChecking=no `
    -r `
    ${RepoRoot}\.env `
    ${User}@${Host}:${RemoteDir}/

# 4. Restart systemd service (or create if not exists)
Write-Host "[deploy] Checking/restarting service..." -ForegroundColor Cyan
plink -pw $Password -P 22 ${User}@${Host} "sudo systemctl is-active running-tracker && sudo systemctl restart running-tracker || echo 'SERVICE_NOT_FOUND'" | Out-Null

Write-Host "[deploy] Done. Check service: ssh ${User}@${Host} 'systemctl status running-tracker'" -ForegroundColor Green
