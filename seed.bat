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
cd /d "%BACKEND_DIR%"
python seed.py

echo.
echo [INFO] Seeding completed successfully.
echo ============================================================
endlocal
