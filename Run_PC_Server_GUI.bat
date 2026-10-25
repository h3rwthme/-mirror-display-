@echo off
title Extend Display Server Launcher
cd /d "%~dp0"

echo ===================================================
echo     EXTEND DISPLAY - PC SERVER GUI LAUNCHER
echo ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak terdeteksi di sistem!
    echo Silakan install Python 3.10+ dari python.org atau Microsoft Store.
    echo Pastikan centang "Add Python to PATH" saat instalasi.
    echo.
    pause
    exit /b 1
)

echo Menjalankan GUI Extend Display Server...
start "" python "pc_server\gui.py"
exit
