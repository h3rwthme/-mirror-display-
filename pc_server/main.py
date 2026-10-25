import argparse
import logging
import signal
import sys
import time

from adb_manager import ADBBridgeManager
from audio_streamer import AudioLoopbackServer
from config import DEFAULT_VIRTUAL_MONITOR_INDEX, PORT_AUDIO, PORT_CONTROL, PORT_DISPLAY
from control_terminal_server import ControlAndTerminalServer
from display_streamer import DisplayStreamServer, VirtualMonitorGeometry


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Professional Dual-Mode Remote Display & Extend Monitor Server (PC)"
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=DEFAULT_VIRTUAL_MONITOR_INDEX,
        help="Indeks monitor target (1 = Primary, 2 = Virtual Display IddSampleDriver)",
    )
    parser.add_argument(
        "--no-adb",
        action="store_true",
        help="Nonaktifkan watcher otomatis `adb reverse` untuk Mode Kabel USB",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("MainServer")

    logger.info("===================================================================")
    logger.info("  EXTEND DISPLAY SERVER - DUAL-MODE (USB ADB/Tether & VPN/Tailscale)")
    logger.info("===================================================================")

    # Shared geometry state antara Socket 1 (Capture) dan Socket 2 (Touch Mouse Injection)
    geometry = VirtualMonitorGeometry(monitor_index=args.monitor)

    # 1. Jalankan Watcher Otomatis ADB Reverse (Mode Kabel USB)
    adb_manager = None
    if not args.no_adb:
        adb_manager = ADBBridgeManager(ports=[PORT_DISPLAY, PORT_CONTROL, PORT_AUDIO])
        adb_manager.start_background_watcher()

    # 2. Jalankan 3 Socket Server Paralel (Multi-Socket Multiplexing)
    display_server = DisplayStreamServer(geometry=geometry, port=PORT_DISPLAY)
    control_server = ControlAndTerminalServer(geometry=geometry, port=PORT_CONTROL)
    audio_server = AudioLoopbackServer(port=PORT_AUDIO)

    display_server.start_in_thread()
    control_server.start_in_thread()
    audio_server.start_in_thread()

    logger.info("Semua layanan aktif. Tekan Ctrl+C untuk menghentikan server.")

    stop_flag = False

    def handle_sigint(sig, frame):
        nonlocal stop_flag
        stop_flag = True

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while not stop_flag:
            time.sleep(0.5)
    finally:
        logger.info("Menghentikan semua layanan socket...")
        if adb_manager:
            adb_manager.stop()
        display_server.stop()
        control_server.stop()
        audio_server.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
