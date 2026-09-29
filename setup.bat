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
        
        echo [INFO] Generating secure secret keys...
        python -c "import secrets; p=r'%BACKEND_DIR%\.env'; c=open(p).read(); c=c.replace('APP_SECRET_KEY=change-me-to-a-secure-random-string', f'APP_SECRET_KEY={secrets.token_hex(32)}').replace('JWT_SECRET_KEY=your-jwt-secret-key-here', f'JWT_SECRET_KEY={secrets.token_hex(32)}'); open(p,'w').write(c)"
        
        echo [OK] Created backend\.env and generated secure secret keys
        
        echo.
        echo [INFO] Database Configuration
        set /p config_db="Do you want to configure database credentials now? (y/n): "
        if /i "!config_db!"=="y" (
            set DB_USER=
            set /p DB_USER="PostgreSQL Username [postgres]: "
            if not defined DB_USER set DB_USER=postgres
            
            set DB_PASS=
            set /p DB_PASS="PostgreSQL Password: "
            
            set DB_HOST=
            set /p DB_HOST="PostgreSQL Host [localhost]: "
            if not defined DB_HOST set DB_HOST=localhost
            
            set DB_PORT=
            set /p DB_PORT="PostgreSQL Port [5432]: "
            if not defined DB_PORT set DB_PORT=5432
            
            set DB_NAME=
            set /p DB_NAME="Database Name [bananavision]: "
            if not defined DB_NAME set DB_NAME=bananavision
            
            set "NEW_DB_URL=postgresql+asyncpg://!DB_USER!:!DB_PASS!@!DB_HOST!:!DB_PORT!/!DB_NAME!"
            
            :: Need to pass via env var to python
            set "NEW_DB_URL=postgresql+asyncpg://!DB_USER!:!DB_PASS!@!DB_HOST!:!DB_PORT!/!DB_NAME!"
            python -c "import os, re; p=r'%BACKEND_DIR%\.env'; c=open(p).read(); c=re.sub(r'^DATABASE_URL=.*', 'DATABASE_URL=' + os.environ.get('NEW_DB_URL', ''), c, flags=re.MULTILINE); open(p,'w').write(c)"
            echo [OK] Database configuration saved to .env
        ) else (
            echo [INFO] Skipping database configuration. ^(Using defaults^)
        )
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
