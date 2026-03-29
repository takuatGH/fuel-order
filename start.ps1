# FuelFlow POC - Startup Script (PowerShell)
# Run: .\start.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "   FuelFlow POC Startup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Host "[!] Docker is not running. Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "[*] Waiting for Docker to start (30 seconds)..." -ForegroundColor Gray
    Start-Sleep -Seconds 30
}

Write-Host "[1/4] Starting PostgreSQL and Redis..." -ForegroundColor Green
docker compose -f docker/docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Failed to start containers. Is Docker running?" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Waiting for database to be ready..." -ForegroundColor Gray
Start-Sleep -Seconds 5

Write-Host "[2/4] Checking database status..." -ForegroundColor Green
$dbCheck = docker exec fuelflow_db psql -U postgres -d fuelflow -c "SELECT 1" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Database not initialized. Setting up..." -ForegroundColor Yellow
    docker exec fuelflow_db psql -U postgres -c "CREATE DATABASE fuelflow;" 2>$null
    docker exec fuelflow_db psql -U postgres -d fuelflow -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    Write-Host "[*] Database created and PostGIS enabled." -ForegroundColor Green
} else {
    Write-Host "[*] Database already exists." -ForegroundColor Green
}

Write-Host "[3/4] Activating conda environment..." -ForegroundColor Green
conda activate fuel-order

Write-Host "[4/4] Starting FastAPI server..." -ForegroundColor Green
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "   FuelFlow is starting!" -ForegroundColor Cyan
Write-Host "   API: http://localhost:8000" -ForegroundColor White
Write-Host "   Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host ""

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
