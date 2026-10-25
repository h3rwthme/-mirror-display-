import logging
import socket
import struct
import threading
import time
import pyaudiowpatch as pyaudio

from config import (
    HOST_BIND,
    PORT_AUDIO,
    detect_connection_mode,
    get_profile,
)

logger = logging.getLogger("AudioStreamer")

# Handshake awal Socket 3 (8 bytes Big-Endian):
# - Sample Rate (uint32, misal 48000)
# - Channels (uint16, misal 2)
# - Bits Per Sample (uint16, misal 16)
AUDIO_CONFIG_STRUCT = struct.Struct(">IHH")

# Header per paket audio (16 bytes Big-Endian):
# - Sequence Number: uint32 (I)
# - Timestamp (ms): uint64 (Q)
# - Payload Length: uint32 (I)
AUDIO_PACKET_HEADER_STRUCT = struct.Struct(">IQI")


class AudioLoopbackServer:
    """
    Socket 3 (PORT 5003): Menangkap System Sound Output PC secara real-time
    menggunakan Windows WASAPI Loopback (pyaudiowpatch) dan mengalirkannya ke tablet.
    """

    def __init__(self, port: int = PORT_AUDIO):
        self.port = port
        self._stop_event = threading.Event()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="AudioServerThread", daemon=True)
        thread.start()
        return thread

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((HOST_BIND, self.port))
            server_sock.listen(2)
            logger.info(f"[Socket 3 - Audio WASAPI] Mendengarkan pada {HOST_BIND}:{self.port}")

            while not self._stop_event.is_set():
                try:
                    client_sock, addr = server_sock.accept()
                except OSError:
                    break
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    name=f"AudioClient-{addr[0]}",
                    daemon=True,
                ).start()

    def _handle_client(self, client_sock: socket.socket, addr: tuple[str, int]):
        peer_ip = addr[0]
        client_hint = None

        try:
            client_sock.settimeout(1.5)
            try:
                first_byte = client_sock.recv(1)
                if first_byte:
                    client_hint = first_byte[0]
            except socket.timeout:
                pass

            mode = detect_connection_mode(peer_ip, client_hint)
            profile = get_profile(mode)

            # Matikan Nagle's Algorithm untuk mencegah jitter paket audio PCM
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, profile.socket_sndbuf_bytes)
            client_sock.settimeout(5.0)

            self._stream_wasapi_loopback(client_sock, peer_ip, mode, profile)
        except (ConnectionResetError, BrokenPipeError, socket.timeout, OSError) as exc:
            logger.info(f"[Socket 3 - Audio WASAPI] Client {peer_ip} terputus ({exc})")
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _stream_wasapi_loopback(self, client_sock: socket.socket, peer_ip: str, mode, profile):
        with pyaudio.PyAudio() as p:
            try:
                loopback_device = p.get_default_wasapi_loopback()
            except OSError as exc:
                logger.error(f"[Socket 3 - Audio WASAPI] Perangkat WASAPI Loopback tidak ditemukan: {exc}")
                return

            sample_rate = int(loopback_device["defaultSampleRate"])
            channels = int(loopback_device["maxInputChannels"])
            chunk_frames = profile.audio_chunk_frames

            logger.info(
                f"[Socket 3 - Audio WASAPI] Client {peer_ip} ({mode.value}) | "
                f"Device: {loopback_device['name']} | {sample_rate}Hz, {channels}ch | "
                f"Chunk: {chunk_frames} frames"
            )

            # Kirim 8-byte konfigurasi audio ke Android agar AudioTrack terinisialisasi akurat
            config_header = AUDIO_CONFIG_STRUCT.pack(sample_rate, channels, 16)
            client_sock.sendall(config_header)

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                frames_per_buffer=chunk_frames,
                input=True,
                input_device_index=loopback_device["index"],
            )

            seq_num = 0
            try:
                while not self._stop_event.is_set():
                    pcm_bytes = stream.read(chunk_frames, exception_on_overflow=False)
                    seq_num = (seq_num + 1) & 0xFFFFFFFF
                    ts_ms = int(time.time() * 1000)
                    pkt_header = AUDIO_PACKET_HEADER_STRUCT.pack(seq_num, ts_ms, len(pcm_bytes))
                    client_sock.sendall(pkt_header + pcm_bytes)
            finally:
                stream.stop_stream()
                stream.close()

    def stop(self):
        self._stop_event.set()
