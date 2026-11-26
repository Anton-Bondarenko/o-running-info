# Docker build & deploy script for running-tracker
# Uploads app files to server, builds image REMOTELY on RasPi, starts container.
# Rationale: local Windows has blocked TLS to pypi.org; server (aarch64) can pull packages fine.
# Usage: .\docker-build.ps1  /  .\docker-build.ps1 -Up -Logs  /  .\docker-build.ps1 -Down

param(
    [switch]$Up,
    [switch]$Down,
    [switch]$Logs,
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root | Out-Null

# === Load .env variables ===
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\w+=.*' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}

if (-not $env:DEPLOY_USER -or -not $env:DEPLOY_PASSWORD) {
    Write-Host "ERROR: DEPLOY_USER and DEPLOY_PASSWORD must be set in .env" -ForegroundColor Red
    exit 1
}

$hostName = if ($env:DEPLOY_HOST)       { $env:DEPLOY_HOST } else { 'raspinas' }
$username  = $env:DEPLOY_USER
$pass      = $env:DEPLOY_PASSWORD
$port      = if ($env:SSH_PORT)         { $env:SSH_PORT }     else { '22' }
$remoteAppDir = if ($env:REMOTE_APP_DIR){ $env:REMOTE_APP_DIR}else { '/home/claude/o-running-info/running-tracker' }
$dbPath    = if ($env:REMOTE_DB_DIR)    { $env:REMOTE_DB_DIR }else { '/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/running-tracker-data' }

# Use function to avoid '$username@' being misinterpreted as a drive operator
function Run-Ssh { Invoke-Expression "plink -P $port -pw `"$pass`" $username`@$hostName @Args" }

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  running-tracker deploy" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "[*] Target:    $($username)@${hostName}:${port}" -ForegroundColor Yellow
Write-Host "[*] Remote app: ${remoteAppDir}" -ForegroundColor Yellow
Write-Host "[*] DB path:    ${dbPath}" -ForegroundColor Yellow

# === Down mode ===
if ($Down) {
    Write-Host "`n[*] Bringing stack down..."
    $rc = Run-Ssh "cd '$remoteAppDir' && docker compose down 2>&1"
    Write-Host $rc
    Pop-Location
    return
}

# === Ensure remote directory exists ===
Write-Host "`n[*] Ensuring remote directories..."
Run-Ssh "mkdir -p '$remoteAppDir/app/app/static/fonts' '$dbPath/running-tracker-data' 2>&1" | Out-Null

# === Upload config files ===
function Send-RemoteFile {
    param([string]$localPath, [string]$remotePath)
    if (-not (Test-Path $localPath)) { return }
    Write-Host "    Sending: $(Split-Path $localPath -Leaf)" -ForegroundColor Gray

    # Remove if it's a directory (prevents cat > creating file in wrong place)
    Run-Ssh "test -d '$remotePath' && rmdir '$remotePath'; true" | Out-Null
    # Truncate remote file
    Run-Ssh "cat > '$remotePath' < /dev/null" | Out-Null

    $content = Get-Content $localPath -Raw -Encoding UTF8
    $len = $content.Length
    for ($i = 0; $i -lt $len; $i += 400000) {
        $chunkLen = [Math]::Min(400000, $len - $i)
        $chunk = $content.Substring($i, $chunkLen)
        $cf = "$env:TEMP\rt-fchunk.txt"
        [IO.File]::WriteAllText($cf, $chunk)
        Get-Content $cf -Raw | Run-Ssh "cat >> '$remotePath'" | Out-Null
        Remove-Item $cf -Force -ErrorAction SilentlyContinue
    }
}

function Sync-Dir {
    param([string]$localBase, [string]$remotePrefix)
    Get-ChildItem $localBase -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Replace($localBase + '\', '').Replace('\', '/')
        if ($_.Extension.ToLower() -match '\.(ttf|otf|woff2?|png|jpg|gif|ico|svg|gz|zip)$') {
            # Binary file: use base64 via PowerShell on server
            $b64f = [Convert]::ToBase64String([IO.File]::ReadAllBytes($_.FullName))
            Run-Ssh "echo '$b64f' | base64 -d > '$remotePrefix/$rel'" | Out-Null
        } else {
            Send-RemoteFile $_.FullName "$remoteAppDir$remotePrefix/$rel"
        }
    }
}

Write-Host "`n[*] Uploading files..."

# docker-compose.yml (use 'build' directive for remote build)
$composeYml = @"
services:
  running-tracker:
    build: .
    container_name: running-tracker
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ${dbPath}:/app/data
      - ${remoteAppDir}/.env:/app/.env:ro
    environment:
      - SERVER_HOST=0.0.0.0
      - SERVER_PORT=8000
      - WORKERS=1
"@

$composeTmp = "$env:TEMP\rt-compose.yml"
[IO.File]::WriteAllText($composeTmp, $composeYml)
Send-RemoteFile $composeTmp "$remoteAppDir/docker-compose.yml"
Remove-Item $composeTmp -Force -ErrorAction SilentlyContinue

# .env on server
$serverEnv = @"
REMOTE_DB_DIR=${dbPath}
REMOTE_DATABASE_URL=sqlite:////srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/running-tracker-data/tracker.db
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
WORKERS=1
"@

$envTmp = "$env:TEMP\rt-server-env"
[IO.File]::WriteAllText($envTmp, $serverEnv)
Send-RemoteFile $envTmp "$remoteAppDir/.env"
Remove-Item $envTmp -Force -ErrorAction SilentlyContinue

# Root files
@('requirements.txt', 'run_server.py') | ForEach-Object {
    if (Test-Path $_) { Send-RemoteFile $_ "$remoteAppDir/$_" }
}

# App directory
Sync-Dir $root '/app'

# Dockerfile
if (Test-Path 'Dockerfile') {
    $dockerfileContent = @"
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && `
    apt-get install -y --no-install-recommends curl && `
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "run_server.py"]
"@
    $dockerTmp = "$env:TEMP\rt-Dockerfile"
    [IO.File]::WriteAllText($dockerTmp, $dockerfileContent)
    Send-RemoteFile $dockerTmp "$remoteAppDir/Dockerfile"
    Remove-Item $dockerTmp -Force -ErrorAction SilentlyContinue
}

Write-Host "[+] Files synced."

# === Build & Up ===
$buildArg = if ($Rebuild) { ' --no-cache' } else { '' }

Write-Host "`n[*] Building image on server..."
$rc = Run-Ssh "cd '$remoteAppDir' && docker compose build$buildArg 2>&1"
Write-Host $rc

if (-not $Logs) {
    Write-Host "`n[*] Starting container..."
    $rc = Run-Ssh "cd '$remoteAppDir' && docker compose up -d 2>&1"
    Write-Host $rc

    Start-Sleep -Seconds 3
    Write-Host "`n[*] Checking health..."
    $health = (Run-Ssh "curl -s http://localhost:8000/ | head -c 200")
    if ($health -match 'DOCTYPE|running-tracker') {
        Write-Host ""
        Write-Host "==============================" -ForegroundColor Green
        Write-Host "[+] App running!" -ForegroundColor Green
        Write-Host "[+] http://$($hostName):8000" -ForegroundColor Green
        Write-Host "==============================" -ForegroundColor Green
    } else {
        Write-Host "[!] Health check unclear. Check logs:" -ForegroundColor Yellow
        Write-Host "    .\docker-build.ps1 -Logs" -ForegroundColor Gray
    }

    Write-Host "`n[+] Deploy complete." -ForegroundColor Green
} else {
    Write-Host "`n[*] Starting and following logs..."
    Run-Ssh "cd '$remoteAppDir' && docker compose up -d && docker logs -f running-tracker"
}

Pop-Location
