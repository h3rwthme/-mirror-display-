import logging
import shutil
import subprocess
import threading
import time
from config import PORT_DISPLAY, PORT_CONTROL, PORT_AUDIO

logger = logging.getLogger("ADBBridgeManager")


class ADBBridgeManager:
    """
    Mengelola jembatan USB ADB (`adb reverse`) secara otomatis di latar belakang.
    Saat tablet Android dicolokkan via USB dengan USB Debugging aktif, ketiga port
    multiplexing (5001, 5002, 5003) langsung di-tunnel ke localhost PC (127.0.0.1).
    """

    @staticmethod
    def find_adb_executable() -> str:
        in_path = shutil.which("adb")
        if in_path:
            return in_path
        import os
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
            if os.path.exists(candidate):
                return candidate
        return "adb"

    def __init__(self, ports: list[int] | None = None, poll_interval_sec: float = 3.0):
        self.ports = ports or [PORT_DISPLAY, PORT_CONTROL, PORT_AUDIO]
        self.poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._active_devices: set[str] = set()
        self.adb_path = self.find_adb_executable()

    def _run_adb(self, args: list[str]) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                [self.adb_path, *args],
                capture_output=True,
                text=True,
                timeout=4.0,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return proc.returncode, (proc.stdout + proc.stderr).strip()
        except FileNotFoundError:
            return -1, "Executable 'adb' tidak ditemukan di PATH."
        except Exception as exc:
            return -1, str(exc)

    def get_connected_devices(self) -> list[str]:
        code, output = self._run_adb(["devices"])
        if code != 0:
            return []
        devices = []
        for line in output.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def apply_reverse_ports(self, serial: str) -> bool:
        """Menjalankan `adb -s <serial> reverse tcp:PORT tcp:PORT` untuk semua socket."""
        success = True
        for port in self.ports:
            code, out = self._run_adb(["-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"])
            if code != 0:
                logger.warning(f"[ADB] Gagal memasang reverse tcp:{port} pada {serial}: {out}")
                success = False
        if success:
            logger.info(
                f"[ADB] Tunnel USB aktif untuk device '{serial}' -> "
                f"tcp:{self.ports} (Tablet cukup konek ke 127.0.0.1)"
            )
        return success

    def start_background_watcher(self) -> threading.Thread:
        """Memantau hot-plug kabel USB tablet secara otomatis."""
        thread = threading.Thread(target=self._watch_loop, name="ADBWatcherThread", daemon=True)
        thread.start()
        return thread

    def _watch_loop(self):
        code, out = self._run_adb(["start-server"])
        if code != 0:
            logger.warning(f"[ADB] Tidak dapat memulai ADB server ({out}). Mode Kabel tetap bisa memakai USB Tethering.")
            return

        while not self._stop_event.is_set():
            current_devices = set(self.get_connected_devices())
            new_devices = current_devices - self._active_devices
            removed_devices = self._active_devices - current_devices

            for serial in new_devices:
                logger.info(f"[ADB] Tablet USB terdeteksi: {serial}. Memasang port reverse...")
                self.apply_reverse_ports(serial)

            for serial in removed_devices:
                logger.info(f"[ADB] Tablet USB dilepas: {serial}.")

            self._active_devices = current_devices
            self._stop_event.wait(self.poll_interval_sec)

    def stop(self):
        self._stop_event.set()
