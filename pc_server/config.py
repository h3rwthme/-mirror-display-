from dataclasses import dataclass
from enum import Enum
import ipaddress


class ConnectionMode( str, Enum ):
    USB_CABLE = "USB_CABLE"      # Via ADB Reverse (127.0.0.1) atau USB Tethering (RNDIS)
    REMOTE_VPN = "REMOTE_VPN"    # Via Tailscale / WireGuard / ZeroTier / WAN


@dataclass
class StreamProfile:
    name: str
    target_fps: int
    jpeg_quality: int
    min_jpeg_quality: int
    max_jpeg_quality: int
    resolution_scale: float
    socket_sndbuf_bytes: int
    audio_chunk_frames: int      # Jumlah sampel per paket pada 48kHz
    max_frame_send_ms: float     # Ambang batas waktu kirim sebelum frame-drop


# Profil Mode Kabel USB (Zero-Lag, Ultra-HD)
USB_PROFILE = StreamProfile(
    name="USB_CABLE_ULTRA_HD",
    target_fps=60,
    jpeg_quality=92,
    min_jpeg_quality=85,
    max_jpeg_quality=95,
    resolution_scale=1.0,
    socket_sndbuf_bytes=64 * 1024,   # 64 KB minimal buffer agar tidak ada antrean frame lama
    audio_chunk_frames=480,          # 10 ms per paket pada 48000 Hz (ultra-low latency)
    max_frame_send_ms=14.0,
)

# Profil Mode Jarak Jauh / VPN (Hemat Bandwidth, Adaptif terhadap Jitter Seluler)
VPN_PROFILE = StreamProfile(
    name="REMOTE_VPN_ADAPTIVE",
    target_fps=30,
    jpeg_quality=65,
    min_jpeg_quality=45,
    max_jpeg_quality=72,
    resolution_scale=0.85,
    socket_sndbuf_bytes=256 * 1024,  # 256 KB untuk menyerap fluktuasi jaringan seluler/VPN
    audio_chunk_frames=1920,         # 40 ms per paket pada 48000 Hz (stabil terhadap jitter)
    max_frame_send_ms=30.0,
)

# Konfigurasi Port Multi-Socket Multiplexing
HOST_BIND = "0.0.0.0"
PORT_DISPLAY = 5001   # Socket 1: Display Stream (IddSampleDriver Virtual Monitor)
PORT_CONTROL = 5002   # Socket 2: Input (Mouse/Keyboard) & Interactive Terminal (CMD/PS)
PORT_AUDIO = 5003     # Socket 3: WASAPI Loopback Audio Stream

# Indeks monitor target pada MSS / DXCam (Monitor 1 = Primary, Monitor 2 = Virtual Display IddSampleDriver)
DEFAULT_VIRTUAL_MONITOR_INDEX = 2

# Audio Configuration (WASAPI Loopback Standard)
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_SAMPLE_WIDTH = 2  # 16-bit PCM (2 bytes per sample)


def detect_connection_mode(peer_ip: str, client_hint: int | None = None) -> ConnectionMode:
    """
    Mendeteksi secara otomatis apakah klien terhubung via Kabel USB (ADB Reverse / USB Tethering)
    atau Jarak Jauh (Tailscale / WireGuard VPN).
    """
    if client_hint == 1:
        return ConnectionMode.USB_CABLE
    if client_hint == 2:
        return ConnectionMode.REMOTE_VPN

    try:
        ip = ipaddress.ip_address(peer_ip)
        # 1. Loopback (127.0.0.1 / ::1) -> Pasti hasil tunnel `adb reverse tcp:PORT tcp:PORT`
        if ip.is_loopback:
            return ConnectionMode.USB_CABLE

        # 2. Subnet CGNAT Tailscale (100.64.0.0/10) -> Pasti Mode Jarak Jauh (VPN)
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return ConnectionMode.REMOTE_VPN

        # 3. Subnet standar Android USB Tethering (RNDIS / NCM)
        usb_tether_subnets = [
            ipaddress.ip_network("192.168.42.0/24"),
            ipaddress.ip_network("192.168.43.0/24"),
            ipaddress.ip_network("192.168.44.0/24"),
        ]
        if any(ip in net for net in usb_tether_subnets):
            return ConnectionMode.USB_CABLE
    except ValueError:
        pass

    # Default fallback ke REMOTE_VPN agar aman terhadap bandwidth
    return ConnectionMode.REMOTE_VPN


def get_profile(mode: ConnectionMode) -> StreamProfile:
    return USB_PROFILE if mode == ConnectionMode.USB_CABLE else VPN_PROFILE
