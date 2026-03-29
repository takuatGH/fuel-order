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

echo [1/4] Starting PostgreSQL and Redis...
docker compose -f docker/docker-compose.yml up -d
if errorlevel 1 (
    echo [!] Failed to start containers. Is Docker running?
    pause
    exit /b 1
)

REM Wait for database to be ready
echo [*] Waiting for database to be ready...
timeout /t 5 /nobreak >nul

echo [2/4] Checking database status...
docker exec fuelflow_db psql -U postgres -d fuelflow -c "SELECT 1" >nul 2>&1
if errorlevel 1 (
    echo [*] Database not initialized. Setting up...
    
    REM Create database
    docker exec fuelflow_db psql -U postgres -c "CREATE DATABASE fuelflow;" 2>nul
    
    REM Enable PostGIS
    docker exec fuelflow_db psql -U postgres -d fuelflow -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    
    echo [*] Database created and PostGIS enabled.
) else (
    echo [*] Database already exists.
)

echo [3/4] Activating conda environment...
call conda activate fuel-order

echo [4/5] Starting ngrok tunnel...
start "ngrok" %USERPROFILE%\ngrok\ngrok.exe http 8000 --url=hailey-blistery-lauren.ngrok-free.dev

echo [5/5] Starting FastAPI server...
echo.
echo ======================================
echo    FuelFlow is starting!
echo    API:     http://localhost:8000
echo    Public:  https://hailey-blistery-lauren.ngrok-free.dev
echo    Docs:    http://localhost:8000/docs
echo ======================================
echo.
echo Press Ctrl+C to stop the server.
echo.

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
