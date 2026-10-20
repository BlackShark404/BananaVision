@echo off
setlocal

:: ─────────────────────────────────────────────────────────
::  BananaVision — Database Seeder Script (Windows)
:: ─────────────────────────────────────────────────────────

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend

echo ============================================================
echo   BananaVision - Running Database Seeder
echo ============================================================

:: Activate virtual environment
if exist "%BACKEND_DIR%\venv\Scripts\activate.bat" (
    call "%BACKEND_DIR%\venv\Scripts\activate.bat"
) else (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

:: Run the seeder
echo [WARNING] Demo seeding deletes existing application database records, including accounts, scans and history.
echo Use a development database only. Choose N to keep your existing database.
set "reset_demo="
set /p reset_demo="Reset the application database and seed demo data now? (y/N): "
if /i not "%reset_demo%"=="y" (
    echo [INFO] Skipping database seeding.
    exit /b 0
)
pushd "%BACKEND_DIR%"
if errorlevel 1 exit /b 1
python seed.py --reset-demo
set "SEED_EXIT_CODE=%errorlevel%"
popd
if not "%SEED_EXIT_CODE%"=="0" (
    echo [ERROR] Seeding failed. Check the error above.
    exit /b 1
)

echo.
echo [INFO] Seeding completed successfully.
echo ============================================================
endlocal
