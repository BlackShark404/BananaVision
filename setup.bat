@echo off
setlocal

:: ─────────────────────────────────────────────────────────
::  BananaVision — Project Setup Script (Windows)
::  Run this script once to initialize the project environment.
:: ─────────────────────────────────────────────────────────

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo ============================================================
echo   BananaVision - Project Setup (Windows)
echo ============================================================

:: 1. Backend .env
echo [INFO] Setting up backend environment variables...
if not exist "%BACKEND_DIR%\.env" (
    if exist "%BACKEND_DIR%\.env.example" (
        copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env"
        echo [OK] Created backend\.env from .env.example
    ) else (
        echo [WARNING] .env.example not found in backend.
    )
) else (
    echo [INFO] backend\.env already exists, skipping.
)

:: 2. Frontend .env
echo [INFO] Setting up frontend environment variables...
if not exist "%FRONTEND_DIR%\.env" (
    if exist "%FRONTEND_DIR%\.env.development" (
        copy "%FRONTEND_DIR%\.env.development" "%FRONTEND_DIR%\.env"
        echo [OK] Created frontend\.env from .env.development
    ) else (
        echo [INFO] No .env.development found in frontend, skipping.
    )
) else (
    echo [INFO] frontend\.env already exists, skipping.
)

:: 3. Backend Dependencies
echo [INFO] Setting up Python virtual environment and dependencies...
if not exist "%BACKEND_DIR%\venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv "%BACKEND_DIR%\venv"
)
call "%BACKEND_DIR%\venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r "%BACKEND_DIR%\requirements.txt"
echo [OK] Backend dependencies installed.

:: 4. Frontend Dependencies
echo [INFO] Setting up Frontend dependencies...
pushd "%FRONTEND_DIR%"
call npm install --legacy-peer-deps
popd
echo [OK] Frontend dependencies installed.

:: 5. Database Seeding
echo [INFO] Checking Database and Seeding...
echo Note: Make sure your PostgreSQL server is running and the database 'bananavision' is created as per your backend\.env configuration.
set /p seed_db="Do you want to seed the database now? (y/n): "
if /i "%seed_db%"=="y" (
    echo [INFO] Seeding database...
    pushd "%BACKEND_DIR%"
    call venv\Scripts\activate.bat
    python seed.py
    popd
    echo [OK] Database seeded.
) else (
    echo [INFO] Skipping database seeding.
)

echo.
echo ============================================================
echo   Setup Complete! 
echo ============================================================
echo You can now run the application using:
echo   dev.bat
echo.

endlocal
