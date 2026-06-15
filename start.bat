@echo off
setlocal

:: ─────────────────────────────────────────────────────────
::  BananaVision — Edge Node Startup Script (Windows)
::  Starts backend and serves frontend for production.
:: ─────────────────────────────────────────────────────────

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo ============================================================
echo   BananaVision - Edge Node Startup (Production Mode)
echo ============================================================

:: 1. Backend Setup
if not exist "%BACKEND_DIR%\venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv "%BACKEND_DIR%\venv"
    call "%BACKEND_DIR%\venv\Scripts\activate.bat"
    pip install -r "%BACKEND_DIR%\requirements.txt"
) else (
    call "%BACKEND_DIR%\venv\Scripts\activate.bat"
)

:: 2. Frontend Setup
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd "%FRONTEND_DIR%"
    call npm install --legacy-peer-deps
    popd
)

if not exist "%FRONTEND_DIR%\dist" (
    echo [INFO] Building Frontend for Production...
    pushd "%FRONTEND_DIR%"
    call npm run build
    popd
)

:: 3. Clean up ports
echo [INFO] Cleaning up ports 8000 and 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5173" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

:: 4. Start Backend
echo [INFO] Starting Backend (FastAPI Production Mode)...
start "BananaVision Backend" cmd /c "cd /d "%BACKEND_DIR%" && call venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: Give backend a moment to boot
timeout /t 3 /nobreak >nul

:: 5. Start Frontend
echo [INFO] Starting Frontend (Static Serve)...
start "BananaVision Frontend" cmd /c "cd /d "%FRONTEND_DIR%" && npm run preview -- --host 0.0.0.0 --port 5173"

:: 6. Launch Kiosk Mode UI
echo [INFO] Waiting for UI to become available...
timeout /t 3 /nobreak >nul
echo [INFO] Launching Kiosk Interface (Google Chrome)...
start chrome --kiosk "http://localhost:5173/kiosk"

echo.
echo ============================================================
echo   System is now LIVE on your local network.
echo   Frontend (Kiosk/Dashboard) -^> http://localhost:5173
echo   Backend API                -^> http://localhost:8000
echo ============================================================
echo.

endlocal

