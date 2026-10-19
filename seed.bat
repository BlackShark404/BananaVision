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
pushd "%BACKEND_DIR%"
if errorlevel 1 exit /b 1
python seed.py
if errorlevel 1 (
    popd
    echo [ERROR] Seeding failed. Use an empty development database and check the error above.
    exit /b 1
)
popd

echo.
echo [INFO] Seeding completed successfully.
echo ============================================================
endlocal
