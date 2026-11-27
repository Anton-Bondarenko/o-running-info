# deploy.ps1 — Deploy running-tracker to Raspberry Pi (raspinas)
# Usage: .\deploy.ps1

param(
    [string]$Target = $(if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "raspinas" }),
    [string]$User = $env:DEPLOY_USER,
    [string]$Password = $env:DEPLOY_PASSWORD
)

if (-not $User -or -not $Password) {
    Write-Host "[deploy] ERROR: DEPLOY_USER and DEPLOY_PASSWORD must be set in .env" -ForegroundColor Red
    exit 1
}

$RemoteDir = "/home/$User/o-running-info/running-tracker"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $RepoRoot "running-tracker"
$Dest = "${User}@${Target}:${RemoteDir}"

Write-Host "[deploy] Target: ${User}@${Target}:${RemoteDir}" -ForegroundColor Cyan

try {
    # 1. Create remote directories
    Write-Host "[deploy] Ensuring remote directories exist..." -ForegroundColor Cyan
    plink -pw $Password -P 22 -batch ${User}@${Target} `
        "mkdir -p ${RemoteDir}/data ${RemoteDir}/app/templates/partials ${RemoteDir}/app/static/fonts ${RemoteDir}/app/static/js ${RemoteDir}/tests" >$null

    # 2. Upload root-level files (exclude .git, __pycache__, venv, test-screenshots)
    Write-Host "[deploy] Uploading root files..." -ForegroundColor Cyan
    $rootFiles = @('.env', '.env.local', '.gitignore', 'DEPLOY.md', 'Dockerfile',
                   'entrypoint.sh', 'requirements.txt', 'run_server.py',
                   'running-tracker.service', 'conftest.py')
    foreach ($f in $rootFiles) {
        $localFile = Join-Path $AppDir $f
        if (Test-Path $localFile) {
            pscp -pw $Password -P 22 -batch $localFile "${Dest}/" | Out-Null
        }
    }

    # 3. Upload app/ Python files
    Write-Host "[deploy] Uploading app/ Python files..." -ForegroundColor Cyan
    Get-ChildItem (Join-Path $AppDir "app") -Filter "*.py" -File | ForEach-Object {
        pscp -pw $Password -P 22 -batch $_.FullName "${Dest}/app/" | Out-Null
    }

    # 4. Upload templates
    Write-Host "[deploy] Uploading templates..." -ForegroundColor Cyan
    Get-ChildItem (Join-Path $AppDir "app\templates") -Recurse -File | ForEach-Object {
        pscp -pw $Password -P 22 -batch $_.FullName "${Dest}/app/templates/" | Out-Null
    }

    # 5. Upload static files
    Write-Host "[deploy] Uploading static files..." -ForegroundColor Cyan
    Get-ChildItem (Join-Path $AppDir "app\static") -Recurse -File | ForEach-Object {
        $dir = $_.DirectoryName.Replace($AppDir, "${RemoteDir}/app/static").Replace('\', '/')
        plink -pw $Password -P 22 -batch ${User}@${Target} "mkdir -p ${RemoteDir}/app/static/$($_.DirectoryName.Substring((Join-Path $AppDir 'app\static').Length + 1).Replace('\', '/'))" >$null 2>&1
        pscp -pw $Password -P 22 -batch $_.FullName "${Dest}/app/static/$($_.DirectoryName.Substring((Join-Path $AppDir "app\static").Length + 1).Replace('\', '/'))/" | Out-Null
    }

    # 6. Upload tests directory
    Write-Host "[deploy] Uploading tests..." -ForegroundColor Cyan
    Get-ChildItem (Join-Path $AppDir "tests") -File -Force | ForEach-Object {
        pscp -pw $Password -P 22 -batch $_.FullName "${Dest}/tests/" | Out-Null
    }

    # 7. Upload wheels if present
    if (Test-Path (Join-Path $AppDir "wheels")) {
        Write-Host "[deploy] Uploading wheels..." -ForegroundColor Cyan
        Get-ChildItem (Join-Path $AppDir "wheels") -File | ForEach-Object {
            pscp -pw $Password -P 22 -batch $_.FullName "${Dest}/wheels/" | Out-Null
        }
    }

    # 8. Restart systemd service (or warn if not yet set up)
    Write-Host "[deploy] Checking/restarting service..." -ForegroundColor Cyan
    $svc = plink -pw $Password -P 22 -batch ${User}@${Target} "sudo systemctl is-active running-tracker && sudo systemctl restart running-tracker || echo 'SERVICE_NOT_FOUND'" | Out-String
    if ($svc -match "SERVICE_NOT_FOUND") {
        Write-Host "[deploy] WARNING: systemd service not found yet." -ForegroundColor Yellow
        Write-Host "[deploy] On the Raspberry Pi, run:" -ForegroundColor Yellow
        Write-Host "  sudo cp ${RemoteDir}/running-tracker.service /etc/systemd/system/"
        Write-Host "  sudo systemctl daemon-reload && sudo systemctl enable --now running-tracker" -ForegroundColor Yellow
    } else {
        Write-Host "[deploy] Service restarted successfully." -ForegroundColor Green
    }

    Write-Host "`n[deploy] Done! Server: http://${Target}:8000" -ForegroundColor Green
} finally {
    Set-Location (Split-Path $MyInvocation.MyCommand.Path)
}
