@echo off
setlocal

:: ─────────────────────────────────────────────────────────
::  BananaVision — Dev Startup Script (Windows)
::  Starts both backend (FastAPI) and frontend (Vite) servers.
::  Usage: dev.bat
:: ─────────────────────────────────────────────────────────

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo ============================================================
echo   BananaVision - Development Environment (Windows)
echo ============================================================

:: Check Python venv
if not exist "%BACKEND_DIR%\venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv "%BACKEND_DIR%\venv"
    call "%BACKEND_DIR%\venv\Scripts\activate.bat"
    pip install -r "%BACKEND_DIR%\requirements.txt"
) else (
    call "%BACKEND_DIR%\venv\Scripts\activate.bat"
)

:: Check frontend node_modules
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd "%FRONTEND_DIR%"
    call npm install --legacy-peer-deps
    popd
)

:: Find and kill processes on ports 8000 and 5173
echo [INFO] Cleaning up ports 8000 and 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5173" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

:: Start backend in a new window
echo [INFO] Starting Backend (FastAPI) on http://localhost:8000
start "BananaVision Backend" cmd /c "cd /d "%BACKEND_DIR%" && call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

:: Give backend a moment to boot
timeout /t 3 /nobreak >nul

:: Start frontend in a new window
echo [INFO] Starting Frontend (Vite) on http://localhost:5173
start "BananaVision Frontend" cmd /c "cd /d "%FRONTEND_DIR%" && npm run dev"

:: Start sensor debugger in a new window
echo [INFO] Starting Sensor Debugger
start "BananaVision Sensor Debugger" cmd /c "cd /d "%BACKEND_DIR%" && call venv\Scripts\activate.bat && python debug_sensor.py"

echo.
echo ============================================================
echo   Frontend  -^>  http://localhost:5173
echo   Backend   -^>  http://localhost:8000
echo   API Docs  -^>  http://localhost:8000/docs
echo   Login     -^>  admin / admin
echo ============================================================
echo   Close the opened CLI windows to stop the servers.
echo.

endlocal
