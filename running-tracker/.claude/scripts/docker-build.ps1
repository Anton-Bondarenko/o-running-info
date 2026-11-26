# Docker build & deploy script for running-tracker
# Uploads app files to server, starts container using existing pre-built image.
# Rationale: local Windows has blocked TLS to pypi.org; server (aarch64) can pull packages fine.
# We skip Docker rebuild - upload code via volumes into the existing working image.
# Usage: .\docker-build.ps1  /  .\docker-build.ps1 -Up -Logs  /  .\docker-build.ps1 -Down

param(
    [switch]$Up,
    [switch]$Down,
    [switch]$Logs
)

$ErrorActionPreference = 'Stop'
$scriptDir = if ($PSCommandPath) { Split-Path $PSCommandPath -Parent } else { Split-Path $PSScriptRoot -Absolute }
$root = (Resolve-Path (Join-Path $scriptDir '../..')).Path

# === Logging ===
$logFile = "$env:TEMP\rt-deploy-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
function Write-Log {
    param([string]$msg)
    $timestamp = Get-Date -Format 'HH:mm:ss.fff'
    "$timestamp $msg" | Tee-Object -FilePath $logFile -Append | Out-Null
}
Write-Log "========== START deploy =========="

# === Load .env variables ===
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Write-Log "[*] Loading .env from: $envFile"
    Get-Content $envFile | Where-Object { $_ -match '^\w+=.*' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
    Write-Log "[*] .env loaded (DEPLOY_USER=$env:DEPLOY_USER, DEPLOY_HOST=$env:DEPLOY_HOST)"
}

if (-not $env:DEPLOY_USER -or -not $env:DEPLOY_PASSWORD) {
    Write-Host "ERROR: DEPLOY_USER and DEPLOY_PASSWORD must be set in .env" -ForegroundColor Red
    exit 1
}

# === NOW change working directory to project root ===
Push-Location $root | Out-Null

$hostName = if ($env:DEPLOY_HOST)       { $env:DEPLOY_HOST } else { 'raspinas' }
$username  = $env:DEPLOY_USER
$pass      = $env:DEPLOY_PASSWORD
$port      = if ($env:SSH_PORT)         { $env:SSH_PORT }     else { '22' }
$remoteAppDir = if ($env:REMOTE_APP_DIR){ $env:REMOTE_APP_DIR}else { '/home/claude/o-running-info/running-tracker' }
$dbPath    = if ($env:REMOTE_DB_DIR)    { $env:REMOTE_DB_DIR }else { '/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/running-tracker-data' }

$sshStartTime = 0
function Run-Ssh {
    param([string]$Cmd)
    $tag = "SSH: $($Cmd.Substring(0, [Math]::Min(60, $Cmd.Length)))"
    Write-Log ">>> START $tag"
    $sshStartTime = Get-Date
    try {
        # Single quotes DO NOT survive plink's SSH layer — they get stripped.
        # Use double-quote escaping (`` \" ``) to create literal quotes that reach remote bash intact.
        # The caller passes a PowerShell string where single-quoted vars get expanded locally,
        # and remaining quoting chars become unquoted on the remote side (safe for paths without spaces).
        $result = & plink -batch -P $port -pw $pass $username`@$hostName "$Cmd" 2>&1 | Out-String

        $elapsed = ((Get-Date) - $sshStartTime).TotalSeconds.ToString('F1')
        Write-Log "<<< DONE $tag (${elapsed}s)"
        return $result
    } catch {
        Write-Log "!!! ERROR $tag : $_"
        throw
    }
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  running-tracker deploy" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "[*] Target:    $($username)@${hostName}:${port}" -ForegroundColor Yellow
Write-Host "[*] Remote app: ${remoteAppDir}" -ForegroundColor Yellow
Write-Host "[*] DB path:    ${dbPath}" -ForegroundColor Yellow

# === SSH Connection Recovery ===

function Ensure-SSHAlive {
    $result = Run-Ssh "true" 2>$null
    if ($LASTEXITCODE -ne 0 -or $result -match '\[killed\]') {
        Write-Host "[!] SSH connection lost - reconnecting..." -ForegroundColor Yellow
        try { $result = Run-Ssh "true" } catch {}
        if ($result -match '\[killed\]') {
            Write-Host "[!] Reconnect failed — waiting 5s and trying once more..." -ForegroundColor Yellow
            Start-Sleep -Seconds 5
            $result = Run-Ssh "true"
        }
    }
    return $true
}

# === DB Safety Functions ===

function Test-RemoteDBExists {
    param([string]$dbPath)
    try {
        Ensure-SSHAlive
        $result = Run-Ssh "test -f '$dbPath/tracker.db' && echo EXISTS || echo MISSING"
        return ($result.Trim() -eq 'EXISTS')
    } catch {
        Write-Host "[!] DB check failed (SSH error)" -ForegroundColor Yellow
        return $false
    }
}

function Test-RemoteDBValid {
    param([string]$dbPath)
    try {
        Ensure-SSHAlive
        # Check SQLite magic header and non-zero file size
        $magic = Run-Ssh "xxd -l 16 -p '$dbPath/tracker.db' 2>/dev/null"
        $size  = Run-Ssh "stat -c '%s' '$dbPath/tracker.db' 2>/dev/null || echo 0"
        if ($magic -match '534c69746520666f726d6174203300' -and [int]$size -gt 0) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Backup-RemoteDB {
    param([string]$dbPath, [string]$backupDir)
    Write-Host "`n[!] Database found - creating backup before deploy..." -ForegroundColor Yellow
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Run-Ssh "mkdir -p '$backupDir'" | Out-Null
    $bakPath = "$backupDir/tracker-backup-${timestamp}.db"
    $rc = Run-Ssh "cp '$dbPath/tracker.db' '$bakPath' 2>&1"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[+] Backup saved to $bakPath" -ForegroundColor Green
    } else {
        Write-Host "[!] No data to backup (empty/dangling file)" -ForegroundColor Yellow
    }
}

function Ensure-ValidDBOnHost {
    param([string]$dbPath)
    # Guarantee a valid SQLite DB always exists at bind-mount point BEFORE container starts
    $bakDir = "$dbPath/pre-deploy-backups"

    if (Test-RemoteDBExists $dbPath) {
        Write-Log "[*] DB file found, checking validity..."
        if (-not (Test-RemoteDBValid $dbPath)) {
            Write-Host "[!] DB file exists but is corrupted/empty — replacing with fresh valid DB" -ForegroundColor Yellow
            # Backup first if there's a non-empty file
            $size = Run-Ssh "stat -c '%s' '$dbPath/tracker.db' 2>/dev/null || echo 0"
            if ([int]$size -gt 0) {
                Run-Ssh "mkdir -p '$bakDir'" | Out-Null
                $bakName = "tracker-bad-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".db"
                Run-Ssh "cp '$dbPath/tracker.db' '$bakDir/$bakName' 2>&1" | Out-Null
                Write-Host "[!] Backed up corrupted file" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[+] DB is valid — no action needed." -ForegroundColor Green
            return
        }
    } else {
        Write-Host "[!] No database found at $dbPath — creating new one on host for bind-mount." -ForegroundColor Yellow
        Run-Ssh "mkdir -p '$dbPath' '$bakDir'" | Out-Null
    }

    # Write DB creation script to temp file and upload to server
    $createDbScript = "import sqlite3, sys, os`n" +
        "db = r'$dbPath/tracker.db'`n" +
        "if os.path.exists(db): os.remove(db)`n" +
        "conn = sqlite3.connect(db)`n" +
        "cur = conn.cursor()`n" +
        "cur.execute('CREATE TABLE IF NOT EXISTS athletes (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT, rank TEXT, rusada_status BOOLEAN DEFAULT 0, dispensary_date TEXT, clinic_status TEXT, is_active BOOLEAN DEFAULT 1, deleted_at TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')`n" +
        "cur.execute('CREATE TABLE IF NOT EXISTS trainings (id INTEGER PRIMARY KEY AUTOINCREMENT, athlete_id INTEGER NOT NULL, date DATE, distance_km REAL, FOREIGN KEY(athlete_id) REFERENCES athletes(id))')`n" +
        "conn.commit()`n" +
        "conn.close()`n" +
        "print('OK: valid DB created at ' + db)`n"
    $scriptTmp = "$env:TEMP\rt-create-db.py"
    [IO.File]::WriteAllText($scriptTmp, $createDbScript, [System.Text.UTF8Encoding]::UTF8)
    $remoteScriptPath = "/tmp/rt-create-db-server.py"
    & pscp -batch -P $port -pw $pass $scriptTmp "${username}@${hostName}:${remoteScriptPath}" | Out-Null

    $rc = Run-Ssh "python3 -I '$remoteScriptPath'"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[+] Valid SQLite database ensured at $dbPath/tracker.db" -ForegroundColor Green
    } else {
        Write-Host "[!] ERROR: Could not create DB on host!" -ForegroundColor Red
        Write-Host "    Data will be lost on next deploy!" -ForegroundColor Red
    }
    Remove-Item $scriptTmp -Force -ErrorAction SilentlyContinue
}

# === Down mode ===
if ($Down) {
    Write-Log "[*] Entering DOWN mode"
    Write-Host "`n[*] Bringing stack down..."

    # Safety: backup DB before stopping container
    if (Test-RemoteDBExists $dbPath) {
        Backup-RemoteDB $dbPath "$dbPath"
    } else {
        Write-Host "[!] No database found at $dbPath" -ForegroundColor Yellow
        Write-Host "    Data may be lost - verify the bind-mount directory on host." -ForegroundColor Yellow
    }

    Write-Log "[*] Running: docker compose down"
    $rc = Run-Ssh "cd '$remoteAppDir' && docker compose down 2>&1"
    Write-Log "[+] docker compose down completed"
    Write-Host $rc
    Pop-Location
    return
}

# === Pre-flight DB safety check ===
Write-Log "[*] Checking database integrity..." -ForegroundColor Cyan
$dbExists = Test-RemoteDBExists $dbPath

if ($dbExists) {
    Write-Host "[+] Database exists at $dbPath" -ForegroundColor Green

    # Also check file size to catch empty/corrupted files
    $dbSize = Run-Ssh "stat -c '%s' '$dbPath/tracker.db' 2>/dev/null || echo 0"
    if ([int]$dbSize -lt 1024) {
        Write-Host "[!] Database file too small (${dbSize} bytes) - may be corrupted or empty." -ForegroundColor Yellow
        Write-Host "    A backup will be created before overwriting." -ForegroundColor Yellow
        Backup-RemoteDB $dbPath "$dbPath/pre-deploy-backups"
    }
} else {
    Write-Host "[!] No database found at $dbPath" -ForegroundColor Red
    Write-Host "    The bind-mount directory is empty - data will NOT survive this deploy." -ForegroundColor Red
    Write-Host "    Possible causes:" -ForegroundColor Yellow
    Write-Host "    1. Previous deploy used Docker volume instead of host bind-mount" -ForegroundColor Gray
    Write-Host "    2. Bind-mount directory was never populated on host" -ForegroundColor Gray
    Write-Host "    3. Container wrote to non-persistent storage" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    ACTION REQUIRED:" -ForegroundColor Yellow
    Write-Host "    - If you have a backup, restore it to: $dbPath/tracker.db" -ForegroundColor Gray
    Write-Host "    - Otherwise the app will start with an empty database." -ForegroundColor Gray
}

# === Ensure remote directory exists (safe - never removes data) ===
Write-Host "`n[*] Ensuring remote directories..."
Ensure-SSHAlive
Run-Ssh "mkdir -p '$remoteAppDir/app/static/fonts' '$remoteAppDir/app/templates/partials' '$dbPath'" | Out-Null

# === Upload config files ===
function Send-RemoteFile {
    param([string]$localPath, [string]$remotePath)
    if (-not (Test-Path $localPath)) { return }
    Write-Host "    Sending: $(Split-Path $localPath -Leaf)" -ForegroundColor Gray

    # Remove if it's a directory
    Run-Ssh "test -d '$remotePath' && rmdir '$remotePath'; true" | Out-Null

    # Use pscp for ALL files — no command-line length limits, binary-safe.
    $scpDest = "${username}@${hostName}:${remotePath}"
    & pscp -batch -P $port -pw $pass $localPath $scpDest | Out-Null
}

function Sync-Dir {
    param([string]$localBase, [string]$remotePrefix)
    Get-ChildItem $localBase -Recurse -File | Where-Object {
        $name = $_.Name.ToLower()
        $pathLower = $_.DirectoryName.ToLower()
        # Exclude stray temp files from previous attempts
        if ($name -match '^\.' -or $name -match '^gito-' -or $name -match '^result_' -or $name -match '^test_' -or $name -eq '.env') { return $false }
        # Exclude large/unneeded directories (use -match for substring check)
        if ($pathLower -match '(^|\\)(__pycache__|venv|\.pytest_cache|\.claude|tests|test-screenshots)(\\|$)') { return $false }
        # Only allow known app file types (exclude scripts, configs, test files that are deploy-only)
        $ext = $_.Extension.ToLower()
        if ($ext -in @('.py', '.html', '.css', '.js')) { return $true }
        if ($ext -in @('.sql', '.yml', '.yaml', '.sh', '.service', '.txt')) { return $false }
        if ($ext -match '\.(ttf|otf|woff2?|png|jpg|gif|ico|svg|gz|zip)$') { return $true }
        return $false
    } | ForEach-Object {
        $rel = $_.FullName.Replace($localBase + '\', '').Replace('\', '/')
        $localPath = $_.FullName
        $remotePath = "$remoteAppDir$remotePrefix/$rel"

        # Remove target directory if it exists (pscp needs a file path, not dir)
        Run-Ssh "test -d '$remotePath' && rmdir '$remotePath'; true" | Out-Null

        # Ensure remote parent directory exists before uploading
        $parentDir = Split-Path $remotePath -Parent
        Run-Ssh "mkdir -p '$parentDir'; true" | Out-Null

        # Use pscp for all files — reliable, no command-line length limits
        $scpDest = "${username}@${hostName}:${remotePath}"
        & pscp -batch -P $port -pw $pass $localPath $scpDest | Out-Null
    }
}

Write-Host "`n[*] Uploading files..."

# docker-compose.yml (use existing pre-built image - skip pip install)
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
      - REMOTE_DB_DIR=/app/data
"@

$composeTmp = "$env:TEMP\rt-compose.yml"
[IO.File]::WriteAllText($composeTmp, $composeYml)
Send-RemoteFile $composeTmp "$remoteAppDir/docker-compose.yml"
Remove-Item $composeTmp -Force -ErrorAction SilentlyContinue

# .env on server — REMOTE_DB_DIR must be container-internal path (/app/data), NOT the UUID-based host path
# The bind mount at /app/data overlays the host path; DB data persists there.
$serverEnv = @"
REMOTE_DB_DIR=/app/data
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

# App directory (remotePrefix '/' appends to remoteAppDir = /home/.../running-tracker)
Sync-Dir $root '/'

Write-Host "[+] Files synced."

# === Ensure valid DB exists at bind-mount BEFORE starting container ===
Write-Host "`n[*] Checking database persistence setup..." -ForegroundColor Cyan
Ensure-ValidDBOnHost $dbPath

# === Up (no rebuild - use existing image) ===
Write-Host "`n[*] Stopping any existing container first..."
# Force remove stale container (remove always wins over compose down)
Run-Ssh "docker rm -f running-tracker 2>/dev/null; true" | Out-Null
$rc = Run-Ssh "cd '$remoteAppDir' && docker compose down 2>&1" | Out-Null
# Reconnect after docker compose down (can kill SSH sessions)
Ensure-SSHAlive
Write-Host "`n[*] Starting container (using existing image, no rebuild)..."
$rc = Run-Ssh "cd '$remoteAppDir' && docker compose up -d 2>&1"
Write-Host $rc

if (-not $Logs) {
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
