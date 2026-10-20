@echo off
setlocal DisableDelayedExpansion

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
        if errorlevel 1 exit /b 1
        
        echo [INFO] Generating secure secret keys...
        python -c "import secrets; p=__import__('os').path.join(__import__('os').environ['BACKEND_DIR'], '.env'); c=open(p).read(); c=c.replace('APP_SECRET_KEY=change-me-to-a-secure-random-string', f'APP_SECRET_KEY={secrets.token_hex(32)}').replace('JWT_SECRET_KEY=your-jwt-secret-key-here', f'JWT_SECRET_KEY={secrets.token_hex(32)}'); open(p,'w').write(c)"
        
        if errorlevel 1 exit /b 1
        echo [OK] Created backend\.env and generated secure secret keys
        
        call :configure_database
        if errorlevel 1 exit /b 1
    ) else (
        echo [ERROR] .env.example not found in backend.
        exit /b 1
    )
) else (
    echo [INFO] backend\.env already exists, skipping.
)

:: 2. Frontend .env
echo [INFO] Setting up frontend environment variables...
if not exist "%FRONTEND_DIR%\.env" (
    if exist "%FRONTEND_DIR%\.env.development" (
        copy "%FRONTEND_DIR%\.env.development" "%FRONTEND_DIR%\.env"
        if errorlevel 1 exit /b 1
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
    if errorlevel 1 goto :dependency_error
)
call "%BACKEND_DIR%\venv\Scripts\activate.bat"
if errorlevel 1 goto :dependency_error
python -m pip install --upgrade pip
if errorlevel 1 goto :dependency_error
python -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 goto :dependency_error
echo [OK] Backend dependencies installed.

:: 4. Frontend Dependencies
echo [INFO] Setting up Frontend dependencies...
pushd "%FRONTEND_DIR%"
call npm install --legacy-peer-deps
if errorlevel 1 (
    popd
    goto :dependency_error
)
popd
echo [OK] Frontend dependencies installed.

:: 5. Database Seeding
echo [INFO] Checking Database and Seeding...
echo [WARNING] Demo seeding deletes existing application database records, including accounts, scans and history.
echo It recreates demo data with VPD and current Scan Logs fields. Use a development database only.
echo Seeding requires BOOTSTRAP_ADMIN_PASSWORD. Choose N to keep your existing database.
set "seed_db="
set /p seed_db="Reset the application database and seed demo data now? (y/N): "
if /i "%seed_db%"=="y" (
    echo [INFO] Seeding database...
    call :seed_database
    if errorlevel 1 exit /b 1
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
exit /b 0

:seed_database
pushd "%BACKEND_DIR%"
if errorlevel 1 exit /b 1
python seed.py --reset-demo
set "SEED_EXIT_CODE=%errorlevel%"
popd
if not "%SEED_EXIT_CODE%"=="0" (
    echo [ERROR] Database seeding failed. Check backend\.env and the error above.
    exit /b 1
)
echo [OK] Database seeded.
exit /b 0

:dependency_error
echo [ERROR] Dependency installation failed. Setup stopped before database seeding.
exit /b 1

:configure_database
echo.
echo [INFO] Database Configuration
set "config_db="
set /p config_db="Do you want to configure database credentials now? (y/n): "
if /i not "%config_db%"=="y" exit /b 0
set "DB_USER="
set /p DB_USER="PostgreSQL Username [postgres]: "
if not defined DB_USER set "DB_USER=postgres"
set "DB_PASS="
set /p DB_PASS="PostgreSQL Password: "
set "DB_HOST="
set /p DB_HOST="PostgreSQL Host [localhost]: "
if not defined DB_HOST set "DB_HOST=localhost"
set "DB_PORT="
set /p DB_PORT="PostgreSQL Port [5432]: "
if not defined DB_PORT set "DB_PORT=5432"
set "DB_NAME="
set /p DB_NAME="Database Name [bananavision]: "
if not defined DB_NAME set "DB_NAME=bananavision"
python -c "import os,re; from pathlib import Path; from urllib.parse import quote; e=os.environ; p=Path(e['BACKEND_DIR'])/'.env'; url='postgresql+asyncpg://'+quote(e['DB_USER'],safe='')+':'+quote(e.get('DB_PASS',''),safe='')+'@'+e['DB_HOST']+':'+e['DB_PORT']+'/'+quote(e['DB_NAME'],safe=''); p.write_text(re.sub(r'^DATABASE_URL=.*', lambda _: 'DATABASE_URL='+url, p.read_text(), flags=re.MULTILINE))"
if errorlevel 1 exit /b 1
echo [OK] Database configuration saved to .env
exit /b 0
