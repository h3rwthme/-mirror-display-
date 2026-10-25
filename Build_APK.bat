@echo off
title Build APK - Extend Display Android Client
cd /d "%~dp0\android_client"

echo ========================================================
echo     BUILD APK EXTEND DISPLAY (TANPA ANDROID STUDIO)
echo ========================================================
echo.

echo [1/2] Menjalankan Gradle Wrapper untuk meng-compile APK...
call gradlew.bat assembleDebug

if errorlevel 1 (
    echo.
    echo [ERROR] Build gagal. Pastikan koneksi internet aktif untuk download dependensi pertama kali.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Build BERHASIL!
echo File APK berada di:
echo android_client\app\build\outputs\apk\debug\app-debug.apk
echo.
echo ========================================================
echo  Anda bisa langsung menginstall file app-debug.apk ke HP!
echo ========================================================
echo.
pause
