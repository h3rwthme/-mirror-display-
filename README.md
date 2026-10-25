# 🖥️ Extend / Mirror Display (Dual-Mode Remote Monitor)

Aplikasi remote display dan extend monitor berperforma tinggi yang menghubungkan PC Windows ke tablet / smartphone Android. Mendukung dual-mode: **Mode Kabel USB (ADB Reverse 60 FPS Ultra-Low Latency)** dan **Mode Jarak Jauh (Wi-Fi Lokal / Tailscale VPN)**.

---

## ✨ Fitur Utama

- **Dual-Mode Jaringan Fleksibel:**
  - **Mode Kabel USB (ADB Reverse):** Latensi ultra-rendah (~10-20ms, 60 FPS) tanpa membebani router Wi-Fi.
  - **Mode Jarak Jauh (VPN/Wi-Fi):** Kompatibel dengan Tailscale, WireGuard, atau jaringan Wi-Fi lokal.
- **Multi-Socket Multiplexing:**
  - **Socket 1 (Port 5001):** High-speed Display Streamer (MSS / DXCam capture + adaptif JPEG streaming).
  - **Socket 2 (Port 5002):** Injeksi sentuhan/mouse/keyboard + terminal interaktif PowerShell/CMD dua arah.
  - **Socket 3 (Port 5003):** Audio streaming sistem PC real-time via Windows WASAPI Loopback.
- **GUI Desktop PC Modern:** Dashboard kontrol berbasis Tkinter dark-mode untuk memilih monitor, memeriksa IP lokal, dan memulai/menghentikan server dalam 1 klik.
- **Tanpa Android Studio:** Dilengkapi batch script untuk build APK langsung dari terminal.

---

## 🚀 Panduan Penggunaan Sisi PC (Windows)

### 1. Instalasi Dependensi
Jalankan file:
```cmd
Install_PC_Dependencies.bat
```
Atau secara manual:
```bash
pip install -r pc_server/requirements.txt
```

### 2. Driver Layar Virtual (IddSampleDriver)
Agar Windows memiliki layar monitor kedua (extend desktop) tanpa monitor fisik:
1. Unduh dan install driver gratis [Virtual-Display-Driver](https://github.com/itsmikethetech/Virtual-Display-Driver).
2. Di Windows *Settings > System > Display*, atur Display 2 ke mode **"Extend desktop to this display"**.

### 3. Menjalankan Server
Cukup klik ganda:
```cmd
Run_PC_Server_GUI.bat
```
Lalu klik tombol **▶ START SERVER**.

---

## 📱 Panduan Penggunaan Sisi Android (Tablet / HP)

### 1. Build APK (1 Klik Saja)
Klik ganda:
```cmd
Build_APK.bat
```
File APK akan otomatis ter-compile di:
`android_client/app/build/outputs/apk/debug/app-debug.apk`

### 2. Pasang ke HP / Tablet
- Kirim file `app-debug.apk` ke HP Anda lalu tap **Install**.
- Atau pasang via ADB jika HP terhubung kabel:
  ```powershell
  adb install android_client/app/build/outputs/apk/debug/app-debug.apk
  ```

### 3. Menghubungkan
- **Mode Kabel USB (0-Lag):**
  Aktifkan *USB Debugging* di HP -> Colokkan kabel USB ke PC -> Buka aplikasi -> Tekan tombol **"Mode Kabel (ADB)"**.
- **Mode Jarak Jauh (Wi-Fi / Tailscale VPN):**
  Masukkan IP PC yang tertera pada GUI PC -> Tekan tombol **"Mode Jarak Jauh (VPN/Tailscale)"**.

---

## 📂 Struktur Proyek

```
extend display/
├── android_client/          # Aplikasi Android (Kotlin, Coroutines, Low-Latency Sockets)
│   ├── app/
│   │   ├── src/main/java/   # DisplayStreamClient, ControlTerminalClient, AudioStreamClient, MainActivity
│   │   └── build.gradle.kts
│   ├── build.gradle.kts
│   ├── settings.gradle.kts
│   └── gradlew.bat
├── pc_server/               # Server PC Windows (Python)
│   ├── gui.py               # Modern Desktop GUI
│   ├── main.py              # CLI Server Entrypoint
│   ├── display_streamer.py  # Socket 1: Screen Capture & JPEG Streamer
│   ├── control_terminal_server.py # Socket 2: Touch/Mouse & Terminal PS/CMD
│   ├── audio_streamer.py    # Socket 3: WASAPI Loopback Audio
│   ├── adb_manager.py       # Auto ADB Reverse watcher
│   ├── config.py            # Profil FPS, Quality, & Port Multiplexing
│   └── requirements.txt
├── scripts/
│   └── setup_usb_bridge.ps1 # Utilitas inspeksi IP & ADB reverse
├── Run_PC_Server_GUI.bat    # Launcher 1-klik PC GUI
├── Install_PC_Dependencies.bat # Installer dependensi PC
└── Build_APK.bat            # Builder APK 1-klik
```
