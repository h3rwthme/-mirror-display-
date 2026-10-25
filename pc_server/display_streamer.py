from collections import deque
from dataclasses import dataclass
import logging
import socket
import struct
import threading
import time
import cv2
import mss
import numpy as np

from config import (
    ConnectionMode,
    DEFAULT_VIRTUAL_MONITOR_INDEX,
    HOST_BIND,
    PORT_DISPLAY,
    detect_connection_mode,
    get_profile,
)

logger = logging.getLogger("DisplayStreamer")

# Header Wire Format Socket 1 (19 bytes Big-Endian):
# - Magic: 2s (b"DS")
# - Frame ID: uint32 (I)
# - Timestamp (ms): uint64 (Q)
# - Flags: uint8 (B) -> bit 0: 1=USB, 0=VPN | bit 1: 0=JPEG, 1=H264
# - Payload Length: uint32 (I)
FRAME_HEADER_STRUCT = struct.Struct(">2sIQBI")
FRAME_MAGIC = b"DS"


@dataclass
class VirtualMonitorGeometry:
    """Menyimpan geometri layar virtual IddSampleDriver untuk pemetaan koordinat sentuh."""
    monitor_index: int = DEFAULT_VIRTUAL_MONITOR_INDEX
    left: int = 0
    top: int = 0
    width: int = 1920
    height: int = 1080
    lock: threading.Lock = threading.Lock()

    def update(self, left: int, top: int, width: int, height: int):
        with self.lock:
            self.left = left
            self.top = top
            self.width = width
            self.height = height

    def map_normalized_to_desktop(self, norm_x: float, norm_y: float) -> tuple[int, int]:
        """Memetakan koordinat sentuh (0.0 - 1.0) dari tablet ke piksel absolut monitor virtual."""
        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))
        with self.lock:
            abs_x = self.left + int(norm_x * (self.width - 1))
            abs_y = self.top + int(norm_y * (self.height - 1))
            return abs_x, abs_y


class DisplayStreamServer:
    """
    Socket 1 (PORT 5001): Menangkap layar dari Windows Virtual Display Driver (IddSampleDriver)
    dan mengirimkan stream visual dengan adaptasi otomatis antara Mode Kabel USB dan Mode VPN.
    """

    def __init__(self, geometry: VirtualMonitorGeometry, port: int = PORT_DISPLAY):
        self.geometry = geometry
        self.port = port
        self._stop_event = threading.Event()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="DisplayServerThread", daemon=True)
        thread.start()
        return thread

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((HOST_BIND, self.port))
            server_sock.listen(2)
            logger.info(f"[Socket 1 - Display] Mendengarkan pada {HOST_BIND}:{self.port}")

            while not self._stop_event.is_set():
                try:
                    client_sock, addr = server_sock.accept()
                except OSError:
                    break
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    name=f"DisplayClient-{addr[0]}",
                    daemon=True,
                ).start()

    def _configure_socket(self, sock: socket.socket, sndbuf_size: int):
        # WAJIB: Matikan Nagle's Algorithm agar paket langsung dikirim tanpa penundaan coalescing
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, sndbuf_size)
        sock.settimeout(5.0)

    def _handle_client(self, client_sock: socket.socket, addr: tuple[str, int]):
        peer_ip = addr[0]
        client_hint = None

        try:
            # Baca 1-byte handshake opsional dari client (0x01 = USB, 0x02 = VPN)
            client_sock.settimeout(1.5)
            try:
                first_byte = client_sock.recv(1)
                if first_byte:
                    client_hint = first_byte[0]
            except socket.timeout:
                pass

            mode = detect_connection_mode(peer_ip, client_hint)
            profile = get_profile(mode)
            self._configure_socket(client_sock, profile.socket_sndbuf_bytes)

            logger.info(
                f"[Socket 1 - Display] Client {peer_ip} terhubung | Mode: {mode.value} | "
                f"Target: {profile.target_fps} FPS | JPEG Quality: {profile.jpeg_quality} | "
                f"SO_SNDBUF: {profile.socket_sndbuf_bytes // 1024} KB"
            )

            self._stream_loop(client_sock, mode, profile)
        except (ConnectionResetError, BrokenPipeError, socket.timeout, OSError) as exc:
            logger.info(f"[Socket 1 - Display] Client {peer_ip} terputus ({exc})")
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _stream_loop(self, client_sock: socket.socket, mode: ConnectionMode, profile):
        # Ring buffer ukuran 1 untuk menjamin hanya frame paling mutakhir yang dikirim (Zero-Lag)
        latest_frame_buffer: deque[np.ndarray] = deque(maxlen=1)
        capture_stop = threading.Event()

        def capture_worker():
            with mss.mss() as sct:
                # Pilih Virtual Monitor IddSampleDriver (fallback ke primary jika monitor ke-2 belum aktif)
                mon_idx = self.geometry.monitor_index
                if mon_idx >= len(sct.monitors):
                    logger.warning(
                        f"[Socket 1 - Display] Monitor index {mon_idx} (IddSampleDriver) tidak ditemukan. "
                        f"Menggunakan monitor utama (index 1)."
                    )
                    mon_idx = 1

                monitor = sct.monitors[mon_idx]
                self.geometry.update(
                    left=monitor["left"],
                    top=monitor["top"],
                    width=monitor["width"],
                    height=monitor["height"],
                )
                logger.info(
                    f"[Socket 1 - Display] Menangkap Virtual Monitor #{mon_idx}: "
                    f"{monitor['width']}x{monitor['height']} pada offset ({monitor['left']}, {monitor['top']})"
                )

                target_interval = 1.0 / profile.target_fps
                while not capture_stop.is_set() and not self._stop_event.is_set():
                    t0 = time.perf_counter()
                    sct_img = sct.grab(monitor)
                    # Konversi BGRA ke BGR untuk kompresi OpenCV
                    frame_bgr = np.asarray(sct_img)[:, :, :3]
                    latest_frame_buffer.append(frame_bgr)

                    elapsed = time.perf_counter() - t0
                    sleep_s = target_interval - elapsed
                    if sleep_s > 0:
                        time.sleep(sleep_s)

        cap_thread = threading.Thread(target=capture_worker, name="MSSCaptureWorker", daemon=True)
        cap_thread.start()

        frame_id = 0
        current_quality = profile.jpeg_quality
        frame_interval = 1.0 / profile.target_fps
        flags = 0x01 if mode == ConnectionMode.USB_CABLE else 0x00

        try:
            while not self._stop_event.is_set():
                loop_start = time.perf_counter()

                if not latest_frame_buffer:
                    time.sleep(0.002)
                    continue

                # Ambil frame terbaru; frame lama otomatis terbuang oleh deque(maxlen=1)
                frame = latest_frame_buffer.pop()

                # Downscale adaptif jika Mode Jarak Jauh (VPN) untuk menghemat bandwidth seluler
                if profile.resolution_scale < 0.99:
                    h, w = frame.shape[:2]
                    new_w = int(w * profile.resolution_scale)
                    new_h = int(h * profile.resolution_scale)
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

                # Encode JPEG menggunakan instruksi SIMD (libjpeg-turbo di dalam OpenCV)
                encode_params = [
                    int(cv2.IMWRITE_JPEG_QUALITY), int(current_quality),
                    int(cv2.IMWRITE_JPEG_OPTIMIZE), 0,  # 0 = Prioritaskan kecepatan encode rendah latensi
                ]
                ok, encoded_buf = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue

                payload = encoded_buf.tobytes()
                frame_id = (frame_id + 1) & 0xFFFFFFFF
                timestamp_ms = int(time.time() * 1000)

                header = FRAME_HEADER_STRUCT.pack(
                    FRAME_MAGIC,
                    frame_id,
                    timestamp_ms,
                    flags,
                    len(payload),
                )

                # Ukur durasi pengiriman TCP untuk mendeteksi bottleneck jaringan (backpressure)
                send_t0 = time.perf_counter()
                client_sock.sendall(header + payload)
                send_ms = (time.perf_counter() - send_t0) * 1000.0

                # Adaptasi Kualitas & Frame-Dropping Dinamis (Khususnya pada Mode Jarak Jauh / VPN)
                if send_ms > profile.max_frame_send_ms:
                    # Terjadi kongesti socket: turunkan kualitas JPEG secara bertahap
                    current_quality = max(profile.min_jpeg_quality, current_quality - 5)
                    if mode == ConnectionMode.REMOTE_VPN:
                        # Beri jeda singkat agar antrean TCP di jaringan seluler terkuras (Frame-Drop)
                        time.sleep(min(0.050, (send_ms - profile.max_frame_send_ms) / 1000.0))
                elif send_ms < (profile.max_frame_send_ms * 0.4):
                    # Jaringan lancar: pulihkan kualitas menuju profil maksimum
                    current_quality = min(profile.max_jpeg_quality, current_quality + 1)

                elapsed = time.perf_counter() - loop_start
                remaining = frame_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
        finally:
            capture_stop.set()

    def stop(self):
        self._stop_event.set()
