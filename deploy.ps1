#!/usr/bin/env pwsh
# AI Mentor deploy script — pushes to git and deploys to VPS (ai-mentor.ru)
#
# Architecture:
#   - Backend (api/worker/beat) runs in Docker
#   - Frontend is built via Docker and copied to /var/www/ai-mentor/ (served by host nginx)
#   - Nginx runs on the host (systemd), not in Docker
#
# Usage:
#   .\deploy.ps1                       # auto-detect changed services
#   .\deploy.ps1 -All                  # rebuild everything
#   .\deploy.ps1 -NoCache              # force --no-cache (when dependencies changed)
#   .\deploy.ps1 -Services api,frontend  # explicit services (api and/or frontend)

param(
    [switch]$All,
    [switch]$NoCache,
    [string[]]$Services,
    [switch]$SkipPush
)

$VPS = "root@ai-mentor.ru"
$REMOTE_DIR = "/opt/ai-mentor"
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
    $nginxChanged    = $diff | Where-Object { $_ -match "^nginx/" }
    $reqChanged      = $diff | Where-Object { $_ -match "requirements\.txt" }
    $pkgChanged      = $diff | Where-Object { $_ -match "package\.json|package-lock\.json" }

    $Services = @()
    if ($backendChanged)  { $Services += "api"; Write-OK "Backend changed" }
    if ($frontendChanged) { $Services += "frontend"; Write-OK "Frontend changed" }
    if ($nginxChanged)    { $Services += "nginx"; Write-OK "Nginx config changed" }
    if ($reqChanged -or $pkgChanged) { $NoCache = $true; Write-Warn "Dependencies changed - will use --no-cache" }

    if ($Services.Count -eq 0) {
        Write-Warn "No changes detected. Use -All or -Services to force."
        exit 0
    }
}

if ($All) { $Services = @("api", "frontend") }

$buildApi      = $Services -contains "api"
$buildFrontend = $Services -contains "frontend"
$updateNginx   = $Services -contains "nginx"

$planParts = @()
if ($buildApi)      { $planParts += "backend (api+worker+beat)" }
if ($buildFrontend) { $planParts += "frontend -> /var/www/ai-mentor/" }
if ($updateNginx)   { $planParts += "nginx config" }
Write-Step "Plan: $($planParts -join ', '), no-cache=$NoCache"

# --- Enable maintenance mode ---
Write-Step "Enabling maintenance mode..."
ssh $VPS "mkdir -p $REMOTE_DIR/maintenance-flag; touch $REMOTE_DIR/maintenance-flag/on"
Write-OK "Maintenance mode ON"

# --- Git push ---
if (-not $SkipPush) {
    Write-Step "Pushing to origin/main..."
    git push origin main
    if ($LASTEXITCODE -ne 0) {
        ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
        Write-Error "git push failed"; exit 1
    }
    Write-OK "Push complete"
}

# --- Pull on VPS ---
Write-Step "Pulling on VPS..."
ssh $VPS "cd $REMOTE_DIR; git pull origin main"
if ($LASTEXITCODE -ne 0) {
    ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
    Write-Error "git pull on VPS failed"; exit 1
}
Write-OK "Pull complete"

# --- Build backend ---
if ($buildApi) {
    Write-Step "Building backend (api) on VPS..."
    if ($NoCache) {
        ssh $VPS "cd $REMOTE_DIR; docker compose build --no-cache api"
    } else {
        ssh $VPS "cd $REMOTE_DIR; docker compose build api"
    }
    if ($LASTEXITCODE -ne 0) {
        ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
        Write-Error "Backend build failed"; exit 1
    }
    Write-OK "Backend build complete"

    Write-Step "Restarting api, worker, beat..."
    ssh $VPS "cd $REMOTE_DIR; docker compose up -d api worker beat --force-recreate"
    if ($LASTEXITCODE -ne 0) {
        ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
        Write-Error "Docker restart failed"; exit 1
    }
    Write-OK "Backend restart complete"

    Write-Step "Waiting for API health check..."
    ssh $VPS "for i in `$(seq 1 30); do curl -sf http://localhost:8000/health && break; sleep 2; done"
    Write-OK "API is healthy"
}

# --- Build frontend ---
if ($buildFrontend) {
    Write-Step "Building frontend and deploying to /var/www/ai-mentor/..."
    $nocacheArg = if ($NoCache) { "--no-cache" } else { "" }
    ssh $VPS "cd $REMOTE_DIR; docker build $nocacheArg --target build -t ai-mentor-frontend-build ./frontend && docker run --rm -v /var/www/ai-mentor:/out ai-mentor-frontend-build sh -c 'cp -r /app/dist/* /out/'"
    if ($LASTEXITCODE -ne 0) {
        ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
        Write-Error "Frontend build failed"; exit 1
    }
    Write-OK "Frontend deployed to /var/www/ai-mentor/"
}

# --- Update nginx config ---
if ($updateNginx) {
    Write-Step "Updating nginx config on VPS..."
    ssh $VPS "cp $REMOTE_DIR/nginx/ai-mentor.conf /etc/nginx/sites-available/ai-mentor.conf"
    Write-OK "Config copied"
}

# --- Reload nginx if frontend or config changed ---
if ($buildFrontend -or $updateNginx) {
    Write-Step "Testing and reloading nginx..."
    ssh $VPS "nginx -t && nginx -s reload"
    if ($LASTEXITCODE -ne 0) {
        ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
        Write-Error "Nginx reload failed"; exit 1
    }
    Write-OK "Nginx reloaded"
}

# --- Disable maintenance mode ---
Write-Step "Disabling maintenance mode..."
ssh $VPS "rm -f $REMOTE_DIR/maintenance-flag/on"
Write-OK "Maintenance mode OFF"

# --- Verify ---
Write-Step "Verifying deployment..."
ssh $VPS "cd $REMOTE_DIR; docker compose ps"

Write-Host ""
Write-Host "==> Deploy complete!" -ForegroundColor Green
