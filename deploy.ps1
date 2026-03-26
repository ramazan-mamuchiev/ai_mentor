#!/usr/bin/env pwsh
# Lexiro deploy script — pushes to git and deploys to VPS (82.38.66.177)
#
# Usage:
#   .\deploy.ps1              # auto-detect changed services
#   .\deploy.ps1 -All         # rebuild everything
#   .\deploy.ps1 -NoCache     # force --no-cache (when requirements changed)
#   .\deploy.ps1 -Services api,web  # explicit services

param(
    [switch]$All,
    [switch]$NoCache,
    [string[]]$Services,
    [switch]$SkipPush
)

$VPS = "root@82.38.66.177"
$REMOTE_DIR = "/opt/ipcodex"
$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# --- Detect what changed since last push ---
if (-not $Services -and -not $All) {
    Write-Step "Detecting changed files..."
    $diff = git diff --name-only origin/main..HEAD 2>$null
    if (-not $diff) { $diff = git diff --name-only HEAD~1 2>$null }

    $backendChanged  = $diff | Where-Object { $_ -match "^backend/" }
    $frontendChanged = $diff | Where-Object { $_ -match "^frontend/" }
    $reqChanged      = $diff | Where-Object { $_ -match "requirements\.txt" }
    $pkgChanged      = $diff | Where-Object { $_ -match "package\.json|package-lock\.json" }

    $Services = @()
    if ($backendChanged)  { $Services += "api"; Write-OK "Backend changed" }
    if ($frontendChanged) { $Services += "web"; Write-OK "Frontend changed" }
    if ($reqChanged -or $pkgChanged) { $NoCache = $true; Write-Warn "Dependencies changed - will use --no-cache" }

    if ($Services.Count -eq 0) {
        Write-Warn "No changes detected. Use -All or -Services to force."
        exit 0
    }
}

if ($All) { $Services = @("api", "web") }

$buildServices = $Services -join " "
$restartServices = @($Services)
if ($restartServices -contains "api" -and $restartServices -notcontains "worker") {
    $restartServices += "worker"
}
$restartList = $restartServices -join " "

Write-Step "Plan: build [$buildServices], restart [$restartList], no-cache=$NoCache"

# --- Git push ---
if (-not $SkipPush) {
    Write-Step "Pushing to origin/main..."
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Error "git push failed"; exit 1 }
    Write-OK "Push complete"
}

# --- Pull on VPS ---
Write-Step "Pulling on VPS..."
ssh $VPS "cd $REMOTE_DIR; git pull origin main"
if ($LASTEXITCODE -ne 0) { Write-Error "git pull on VPS failed"; exit 1 }
Write-OK "Pull complete"

# --- Build ---
Write-Step "Building [$buildServices] on VPS..."
if ($NoCache) {
    ssh $VPS "cd $REMOTE_DIR; docker compose build --no-cache $buildServices"
} else {
    ssh $VPS "cd $REMOTE_DIR; docker compose build $buildServices"
}
if ($LASTEXITCODE -ne 0) { Write-Error "docker build failed"; exit 1 }
Write-OK "Build complete"

# --- Restart ---
Write-Step "Restarting [$restartList] on VPS..."
ssh $VPS "cd $REMOTE_DIR; docker compose up -d $restartList --force-recreate"
if ($LASTEXITCODE -ne 0) { Write-Error "docker restart failed"; exit 1 }
Write-OK "Restart complete"

# --- Verify ---
Write-Step "Verifying deployment..."
ssh $VPS "cd $REMOTE_DIR; docker compose ps"

Write-Host ""
Write-Host "==> Deploy complete!" -ForegroundColor Green
