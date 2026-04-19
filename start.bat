@echo off
REM FuelFlow POC - Startup Script
REM Run this to spin up the entire stack

echo ======================================
echo    FuelFlow POC Startup
echo ======================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [!] Docker is not running. Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo [*] Waiting for Docker to start (this may take a minute)...
    timeout /t 30 /nobreak >nul
)

echo [1/6] Starting PostgreSQL and Redis...
docker compose -f docker/docker-compose.yml up -d
if errorlevel 1 (
    echo [!] Failed to start containers. Is Docker running?
    pause
    exit /b 1
)

REM Wait for database to be ready
echo [*] Waiting for database to be ready...
timeout /t 5 /nobreak >nul

echo [2/6] Checking database status...
docker exec fuelflow_db psql -U postgres -d fuelflow -c "SELECT 1" >nul 2>&1
if errorlevel 1 (
    echo [*] Database not initialized. Setting up...
    docker exec fuelflow_db psql -U postgres -c "CREATE DATABASE fuelflow;" 2>nul
    docker exec fuelflow_db psql -U postgres -d fuelflow -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    echo [*] Database created and PostGIS enabled.
) else (
    echo [*] Database already exists.
)

echo [3/6] Activating conda environment...
call conda activate fuel-order

echo [4/6] Running database migrations...
alembic upgrade head
if errorlevel 1 (
    echo [!] Migration failed. Check alembic output above.
    pause
    exit /b 1
)

echo [5/6] Seeding depots and drivers (skips if already present)...
python scripts/seed_depots.py
python scripts/seed_drivers.py

echo [6/6] Starting services...
echo.
echo ======================================
echo    FuelFlow is starting!
echo    API:     http://localhost:8000
echo    Public:  https://hailey-blistery-lauren.ngrok-free.dev
echo    Docs:    http://localhost:8000/docs
echo ======================================
echo.

start "ngrok" %USERPROFILE%\ngrok\ngrok.exe http 8000 --url=hailey-blistery-lauren.ngrok-free.dev
start "ARQ Worker" cmd /k "conda activate fuel-order && arq src.worker.WorkerSettings"

echo Press Ctrl+C to stop the FastAPI server.
echo (Close the ARQ Worker window separately to stop the task queue.)
echo.

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
