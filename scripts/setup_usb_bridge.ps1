<#
.SYNOPSIS
    Script Otomatis Setup Jembatan USB (ADB Reverse) & Inspeksi IP Dual-Mode
    Untuk Aplikasi Extend Display Professional (PC Server <-> Android Tablet)
#>

$Ports = @(5001, 5002, 5003)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  EXTEND DISPLAY - DUAL-MODE NETWORK SETUP UTILITY   " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Periksa keberadaan ADB untuk Mode Kabel (ADB Reverse)
$adbCmd = "adb"
if (-not (Get-Command "adb" -ErrorAction SilentlyContinue)) {
    $fallbackAdb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path $fallbackAdb) {
        $adbCmd = $fallbackAdb
        Write-Host "[INFO] Menggunakan ADB dari: $adbCmd" -ForegroundColor Gray
    }
}

if ((Test-Path $adbCmd) -or (Get-Command "adb" -ErrorAction SilentlyContinue)) {
    Write-Host "`n[1/3] Memeriksa perangkat Android via USB (ADB)..." -ForegroundColor Yellow
    & $adbCmd start-server | Out-Null
    $adbLines = & $adbCmd devices | Select-Object -Skip 1 | Where-Object { $_ -match "\s+device$" }

    if ($adbLines) {
        foreach ($line in $adbLines) {
            $serial = ($line -split "\s+")[0]
            Write-Host "  -> Tablet Terdeteksi: $serial" -ForegroundColor Green
            foreach ($port in $Ports) {
                & $adbCmd -s $serial reverse tcp:$port tcp:$port
                Write-Host "     [+] adb reverse tcp:$port -> tcp:$port OK" -ForegroundColor Green
            }
            Write-Host "  -> Daftar tunnel aktif pada ${serial}:" -ForegroundColor Gray
            & $adbCmd -s $serial reverse --list
        }
        Write-Host "`n  [INFO] Pada aplikasi Android, pilih 'MODE KABEL (ADB)' (Host: 127.0.0.1)" -ForegroundColor Cyan
    } else {
        Write-Host "  [!] Tidak ada tablet dengan USB Debugging aktif yang terdeteksi." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "`n[!] Perintah 'adb' tidak ditemukan di PATH. Lewati setup ADB Reverse." -ForegroundColor Red
}

# 2. Periksa IP USB Tethering (RNDIS) & Tailscale VPN
Write-Host "`n[2/3] Memindai Antarmuka Jaringan PC (USB Tethering & Tailscale VPN)..." -ForegroundColor Yellow
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*"
} | ForEach-Object {
    $ip = $_.IPAddress
    $alias = $_.InterfaceAlias
    if ($ip -like "100.*") {
        Write-Host "  [MODE JARAK JAUH - TAILSCALE/VPN] $alias -> IP: $ip" -ForegroundColor Magenta
    } elseif ($ip -like "192.168.42.*" -or $ip -like "192.168.43.*") {
        Write-Host "  [MODE KABEL - USB TETHERING]      $alias -> IP: $ip" -ForegroundColor Green
    } else {
        Write-Host "  [LAN / WI-FI LOKAL]               $alias -> IP: $ip" -ForegroundColor Gray
    }
}

Write-Host "`n[3/3] Port Multiplexing Server:" -ForegroundColor Yellow
Write-Host "  - TCP 5001 : Socket 1 (Display Stream - IddSampleDriver)"
Write-Host "  - TCP 5002 : Socket 2 (Touch/Mouse/Keyboard + Interactive Terminal)"
Write-Host "  - TCP 5003 : Socket 3 (WASAPI Loopback Audio Stream)"
Write-Host "=====================================================" -ForegroundColor Cyan
