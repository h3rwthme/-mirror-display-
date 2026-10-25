@echo off
title Install Dependencies - Extend Display PC Server
cd /d "%~dp0"

echo =========================================================
echo    INSTALLASI DEPENDENSI PC SERVER (EXTEND DISPLAY)
echo =========================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak terdeteksi!
    echo Silakan unduh dan install Python 3.10+ dari https://www.python.org/downloads/
    echo PENTING: Centang opsi "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Memperbarui pip dan menginstall library Python...
python -m pip install --upgrade pip
python -m pip install -r "pc_server\requirements.txt"
if errorlevel 1 (
    echo.
    echo [WARNING] Ada paket yang gagal diinstall. Pastikan koneksi internet aktif.
    echo.
) else (
    echo [+] Library Python berhasil diinstall.
)

echo.
echo [2/3] Memeriksa Android Debug Bridge (ADB)...
powershell -ExecutionPolicy Bypass -Command "if ((Get-Command 'adb' -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'))) { Write-Host '[+] ADB Terdeteksi dan Siap Digunakan.' -ForegroundColor Green } else { Write-Host '[!] ADB belum terpasang. Fitur kabel USB ADB Reverse memerlukan Android Platform Tools.' -ForegroundColor Yellow }"

echo.
echo [3/3] Informasi Virtual Display Driver:
echo Jika Anda ingin layar extend tanpa monitor fisik kedua, pastikan Anda telah
echo memasang driver 'Virtual-Display-Driver' (IddSampleDriver / Amyuni).
echo.
echo =========================================================
echo  Instalasi selesai! Anda dapat menjalankan:
echo  - Run_PC_Server_GUI.bat (Mode GUI Desktop)
echo  - python pc_server/main.py (Mode Terminal / Konsol)
echo =========================================================
echo.
pause
