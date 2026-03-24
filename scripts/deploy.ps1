<#
.SYNOPSIS
    Deploy IPCodex to VPS (82.38.66.177).

.DESCRIPTION
    Pulls latest code, builds Docker images, and restarts services on VPS.
    Automatically pushes local commits to origin/main before deploying.

.PARAMETER Target
    What to build and restart: api, web, all (default: all).

.PARAMETER NoCache
    Force Docker build without cache (use when requirements.txt or package.json changed).

.PARAMETER SkipPush
    Skip git push (if you already pushed manually).

.EXAMPLE
    .\scripts\deploy.ps1                       # deploy everything
    .\scripts\deploy.ps1 -Target api           # backend only
    .\scripts\deploy.ps1 -Target web           # frontend only
    .\scripts\deploy.ps1 -NoCache              # rebuild without Docker cache
    .\scripts\deploy.ps1 -NoCache -Target api  # backend only, no cache
#>

param(
    [ValidateSet("all", "api", "web")]
    [string]$Target = "all",

    [switch]$NoCache,

    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

$VPS_HOST = "root@82.38.66.177"
$VPS_DIR  = "/opt/ipcodex"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Invoke-VPS($cmd) {
    Write-Host "  > ssh $VPS_HOST `"$cmd`"" -ForegroundColor DarkGray
    ssh $VPS_HOST $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# --- 1. Git push ---
if (-not $SkipPush) {
    Write-Step "Git push"
    git push origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  git push failed" -ForegroundColor Red
        exit 1
    }
}

# --- 2. Pull on VPS ---
Write-Step "Pull on VPS"
Invoke-VPS "cd $VPS_DIR && git pull origin main"

# --- 3. Build ---
switch ($Target) {
    "api" { $buildServices = "api";     $restartServices = "api worker" }
    "web" { $buildServices = "web";     $restartServices = "web" }
    "all" { $buildServices = "api web"; $restartServices = "api worker web" }
}

$buildArgs = if ($NoCache) { "--no-cache" } else { "" }

Write-Step "Build: $buildServices$(if ($NoCache) { ' (--no-cache)' })"
Invoke-VPS "cd $VPS_DIR && docker compose build $buildArgs $buildServices"

# --- 4. Restart ---
Write-Step "Restart: $restartServices"
Invoke-VPS "cd $VPS_DIR && docker compose up -d --force-recreate $restartServices"

# --- 5. Health check ---
Write-Step "Health check"
Start-Sleep -Seconds 3
Invoke-VPS "cd $VPS_DIR && docker compose ps --format 'table {{.Name}}\t{{.Status}}' | grep -E '(api|worker|web)'"

Write-Host ""
Write-Host "Deploy complete!" -ForegroundColor Green
Write-Host ""
