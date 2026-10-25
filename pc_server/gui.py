"""
Extend Display Server - Modern Desktop GUI (PC)
Menyediakan antarmuka grafis yang ramah pengguna untuk mengontrol
Display Streamer, Audio Loopback, Terminal & Input Injection, dan ADB Watcher.
"""

import ipaddress
import logging
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Tambahkan direktori pc_server ke sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adb_manager import ADBBridgeManager
from audio_streamer import AudioLoopbackServer
from config import DEFAULT_VIRTUAL_MONITOR_INDEX, PORT_AUDIO, PORT_CONTROL, PORT_DISPLAY
from control_terminal_server import ControlAndTerminalServer
from display_streamer import DisplayStreamServer, VirtualMonitorGeometry


class QueueLogHandler(logging.Handler):
    """Logging handler yang mengalirkan log ke queue GUI Tkinter."""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(msg)


class ExtendDisplayServerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Extend Display Server - Dual-Mode")
        self.root.geometry("820x680")
        self.root.minsize(720, 560)

        # Palet Warna Dark Mode Modern
        self.BG_DARK = "#121214"
        self.CARD_BG = "#1e1e24"
        self.CARD_BORDER = "#2e2e38"
        self.TEXT_MAIN = "#f4f4f5"
        self.TEXT_MUTED = "#a1a1aa"
        self.ACCENT_BLUE = "#3b82f6"
        self.ACCENT_GREEN = "#10b981"
        self.ACCENT_RED = "#ef4444"
        self.ENTRY_BG = "#272730"

        self.root.configure(bg=self.BG_DARK)

        # Server state
        self.is_running = False
        self.adb_manager = None
        self.display_server = None
        self.control_server = None
        self.audio_server = None
        self.geometry = None

        # Queue untuk log
        self.log_queue = queue.Queue()
        self.setup_logging()

        # Build UI
        self.build_ui()

        # Update log berkala
        self.root.after(100, self.process_log_queue)

        # Refresh IP & ADB awal
        self.root.after(300, self.refresh_network_and_adb)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_logging(self):
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        log_handler = QueueLogHandler(self.log_queue)
        log_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s", "%H:%M:%S")
        )
        root_logger.addHandler(log_handler)

    def build_ui(self):
        # 1. Header Frame
        header = tk.Frame(self.root, bg=self.BG_DARK, padx=20, pady=16)
        header.pack(fill=tk.X)

        title_box = tk.Frame(header, bg=self.BG_DARK)
        title_box.pack(side=tk.LEFT)

        title_lbl = tk.Label(
            title_box,
            text="🖥️ Extend Display Server",
            font=("Segoe UI", 16, "bold"),
            fg=self.TEXT_MAIN,
            bg=self.BG_DARK,
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = tk.Label(
            title_box,
            text="Mode Kabel USB (ADB 0-Lag) & Mode Jarak Jauh (WiFi / Tailscale VPN)",
            font=("Segoe UI", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_DARK,
        )
        subtitle_lbl.pack(anchor=tk.W)

        # Status Pill Badge
        self.status_badge = tk.Label(
            header,
            text="● STOPPED",
            font=("Segoe UI", 10, "bold"),
            fg=self.ACCENT_RED,
            bg="#2a1515",
            padx=12,
            pady=4,
            relief=tk.FLAT,
        )
        self.status_badge.pack(side=tk.RIGHT, pady=6)

        # 2. Main Content Frame (Notebook/Cards)
        main_frame = tk.Frame(self.root, bg=self.BG_DARK, padx=20, pady=6)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Card 1: Pengaturan Server & Target Monitor
        card1 = tk.LabelFrame(
            main_frame,
            text=" ⚙️ Pengaturan Server & Monitor ",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            padx=16,
            pady=12,
            relief=tk.GROOVE,
        )
        card1.pack(fill=tk.X, pady=6)

        c1_row1 = tk.Frame(card1, bg=self.CARD_BG)
        c1_row1.pack(fill=tk.X, pady=4)

        tk.Label(
            c1_row1,
            text="Target Monitor:",
            font=("Segoe UI", 9, "bold"),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.monitor_var = tk.StringVar(value=str(DEFAULT_VIRTUAL_MONITOR_INDEX))
        self.monitor_dropdown = ttk.Combobox(
            c1_row1,
            textvariable=self.monitor_var,
            width=32,
            state="readonly",
        )
        self.populate_monitors()
        self.monitor_dropdown.pack(side=tk.LEFT, padx=(0, 10))

        btn_refresh_monitors = tk.Button(
            c1_row1,
            text="🔄 Refresh Monitor",
            font=("Segoe UI", 9),
            command=self.populate_monitors,
            bg=self.ENTRY_BG,
            fg=self.TEXT_MAIN,
            activebackground=self.CARD_BORDER,
            relief=tk.FLAT,
            padx=8,
            pady=2,
        )
        btn_refresh_monitors.pack(side=tk.LEFT)

        # Checkbox Layanan
        c1_row2 = tk.Frame(card1, bg=self.CARD_BG)
        c1_row2.pack(fill=tk.X, pady=(8, 0))

        self.enable_adb_var = tk.BooleanVar(value=True)
        self.chk_adb = tk.Checkbutton(
            c1_row2,
            text="Otomatis Jembatan USB (ADB Reverse)",
            variable=self.enable_adb_var,
            font=("Segoe UI", 9),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            selectcolor=self.BG_DARK,
            activebackground=self.CARD_BG,
            activeforeground=self.TEXT_MAIN,
        )
        self.chk_adb.pack(side=tk.LEFT, padx=(0, 16))

        self.enable_audio_var = tk.BooleanVar(value=True)
        self.chk_audio = tk.Checkbutton(
            c1_row2,
            text="Audio Stream (WASAPI Loopback)",
            variable=self.enable_audio_var,
            font=("Segoe UI", 9),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            selectcolor=self.BG_DARK,
            activebackground=self.CARD_BG,
            activeforeground=self.TEXT_MAIN,
        )
        self.chk_audio.pack(side=tk.LEFT, padx=(0, 16))

        self.enable_control_var = tk.BooleanVar(value=True)
        self.chk_control = tk.Checkbutton(
            c1_row2,
            text="Touch/Mouse & Terminal",
            variable=self.enable_control_var,
            font=("Segoe UI", 9),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            selectcolor=self.BG_DARK,
            activebackground=self.CARD_BG,
            activeforeground=self.TEXT_MAIN,
        )
        self.chk_control.pack(side=tk.LEFT)

        # Card 2: Informasi IP Jaringan & Status USB ADB
        card2 = tk.LabelFrame(
            main_frame,
            text=" 📡 Informasi Koneksi untuk Tablet / Klien ",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            padx=16,
            pady=10,
            relief=tk.GROOVE,
        )
        card2.pack(fill=tk.X, pady=6)

        self.ip_info_label = tk.Label(
            card2,
            text="Memindai jaringan...",
            font=("Consolas", 9),
            fg="#6ee7b7",
            bg=self.CARD_BG,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self.ip_info_label.pack(fill=tk.X, pady=2)

        c2_actions = tk.Frame(card2, bg=self.CARD_BG)
        c2_actions.pack(fill=tk.X, pady=(6, 0))

        btn_refresh_net = tk.Button(
            c2_actions,
            text="🔄 Scan IP & USB",
            font=("Segoe UI", 9),
            command=self.refresh_network_and_adb,
            bg=self.ENTRY_BG,
            fg=self.TEXT_MAIN,
            activebackground=self.CARD_BORDER,
            relief=tk.FLAT,
            padx=8,
            pady=2,
        )
        btn_refresh_net.pack(side=tk.LEFT, padx=(0, 10))

        self.adb_status_lbl = tk.Label(
            c2_actions,
            text="ADB: Menunggu pemindaian...",
            font=("Segoe UI", 9),
            fg=self.TEXT_MUTED,
            bg=self.CARD_BG,
        )
        self.adb_status_lbl.pack(side=tk.LEFT)

        # Action Buttons (Start / Stop)
        act_frame = tk.Frame(main_frame, bg=self.BG_DARK, pady=8)
        act_frame.pack(fill=tk.X)

        self.btn_toggle_server = tk.Button(
            act_frame,
            text="▶  START SERVER",
            font=("Segoe UI", 11, "bold"),
            command=self.toggle_server,
            bg=self.ACCENT_BLUE,
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            padx=24,
            pady=8,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.btn_toggle_server.pack(side=tk.LEFT, padx=(0, 12))

        btn_clear_log = tk.Button(
            act_frame,
            text="Bersihkan Log",
            font=("Segoe UI", 9),
            command=self.clear_log,
            bg=self.ENTRY_BG,
            fg=self.TEXT_MAIN,
            activebackground=self.CARD_BORDER,
            relief=tk.FLAT,
            padx=12,
            pady=8,
        )
        btn_clear_log.pack(side=tk.RIGHT)

        # Card 3: Real-time Live Log Window
        card3 = tk.LabelFrame(
            main_frame,
            text=" 📝 Live Server Logs ",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_MAIN,
            bg=self.CARD_BG,
            padx=10,
            pady=6,
            relief=tk.GROOVE,
        )
        card3.pack(fill=tk.BOTH, expand=True, pady=4)

        self.log_text = scrolledtext.ScrolledText(
            card3,
            wrap=tk.WORD,
            bg="#0d0d11",
            fg="#a1a1aa",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def populate_monitors(self):
        options = []
        try:
            import mss
            with mss.mss() as sct:
                for idx, m in enumerate(sct.monitors):
                    if idx == 0:
                        continue  # 0 adalah gabungan semua monitor
                    tag = " (Primary)" if idx == 1 else " (Monitor 2 / Virtual)"
                    options.append(f"Monitor {idx}: {m['width']}x{m['height']} at ({m['left']},{m['top']}){tag}")
        except Exception:
            options = [
                "Monitor 1 (Primary Windows)",
                "Monitor 2 (Virtual Display / IddSampleDriver)",
                "Monitor 3",
            ]

        self.monitor_dropdown["values"] = options
        if options:
            # Default ke monitor 2 jika ada > 1 monitor, selain itu monitor 1
            default_choice = options[1] if len(options) > 1 else options[0]
            self.monitor_dropdown.set(default_choice)

    def get_selected_monitor_index(self) -> int:
        val = self.monitor_var.get()
        if val.startswith("Monitor "):
            try:
                num_str = val.split(":")[0].replace("Monitor ", "").strip()
                return int(num_str)
            except ValueError:
                pass
        return DEFAULT_VIRTUAL_MONITOR_INDEX

    def refresh_network_and_adb(self):
        # 1. Pindai IP lokal
        ip_lines = []
        try:
            # Cari IP lokal
            hostname = socket.gethostname()
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            seen_ips = set()
            for item in addr_info:
                ip = item[4][0]
                if ip not in seen_ips and not ip.startswith("127."):
                    seen_ips.add(ip)
                    if ip.startswith("100."):
                        ip_lines.append(f"• Mode Jarak Jauh (Tailscale VPN) : {ip}")
                    elif ip.startswith("192.168.42.") or ip.startswith("192.168.43."):
                        ip_lines.append(f"• Mode Kabel USB (USB Tethering) : {ip}")
                    else:
                        ip_lines.append(f"• Mode Wi-Fi / LAN Lokal         : {ip}")
        except Exception as e:
            ip_lines.append(f"Error memindai IP: {e}")

        ip_lines.append("• Mode Kabel USB (ADB Reverse)   : 127.0.0.1 (Port 5001, 5002, 5003)")

        self.ip_info_label.config(text="\n".join(ip_lines))

        # 2. Pindai ADB
        threading.Thread(target=self._check_adb_async, daemon=True).start()

    def _check_adb_async(self):
        mgr = ADBBridgeManager()
        devices = mgr.get_connected_devices()
        adb_exec = mgr.adb_path
        adb_found = os.path.exists(adb_exec) or (adb_exec == "adb")

        if devices:
            text = f"ADB OK: Terdeteksi {len(devices)} tablet ({', '.join(devices)})"
            color = self.ACCENT_GREEN
        elif adb_found:
            text = "ADB Terpasang, siap (Belum ada tablet USB dengan USB Debugging aktif)"
            color = "#f59e0b"
        else:
            text = "ADB belum ditemukan di PATH atau Android SDK."
            color = self.ACCENT_RED

        self.root.after(0, lambda: self.adb_status_lbl.config(text=text, fg=color))

    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        self.root.after(100, self.process_log_queue)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def toggle_server(self):
        if not self.is_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        monitor_idx = self.get_selected_monitor_index()
        logging.info(f"Memulai Extend Display Server pada Monitor {monitor_idx}...")

        try:
            self.geometry = VirtualMonitorGeometry(monitor_index=monitor_idx)

            # 1. Jalankan ADB Watcher jika aktif
            if self.enable_adb_var.get():
                self.adb_manager = ADBBridgeManager(ports=[PORT_DISPLAY, PORT_CONTROL, PORT_AUDIO])
                self.adb_manager.start_background_watcher()

            # 2. Jalankan Server Sockets
            self.display_server = DisplayStreamServer(geometry=self.geometry, port=PORT_DISPLAY)
            self.display_server.start_in_thread()

            if self.enable_control_var.get():
                self.control_server = ControlAndTerminalServer(geometry=self.geometry, port=PORT_CONTROL)
                self.control_server.start_in_thread()

            if self.enable_audio_var.get():
                self.audio_server = AudioLoopbackServer(port=PORT_AUDIO)
                self.audio_server.start_in_thread()

            self.is_running = True
            self.status_badge.config(text="● RUNNING", fg=self.ACCENT_GREEN, bg="#132a1e")
            self.btn_toggle_server.config(
                text="■  STOP SERVER",
                bg=self.ACCENT_RED,
                activebackground="#dc2626",
            )
            logging.info("Semua socket server aktif dan siap menerima koneksi client.")
        except Exception as exc:
            logging.error(f"Gagal memulai server: {exc}", exc_info=True)
            messagebox.showerror("Error", f"Gagal memulai server: {exc}")
            self.stop_server()

    def stop_server(self):
        logging.info("Menghentikan server...")
        if self.adb_manager:
            try:
                self.adb_manager.stop()
            except Exception:
                pass
            self.adb_manager = None

        if self.display_server:
            try:
                self.display_server.stop()
            except Exception:
                pass
            self.display_server = None

        if self.control_server:
            try:
                self.control_server.stop()
            except Exception:
                pass
            self.control_server = None

        if self.audio_server:
            try:
                self.audio_server.stop()
            except Exception:
                pass
            self.audio_server = None

        self.is_running = False
        self.status_badge.config(text="● STOPPED", fg=self.ACCENT_RED, bg="#2a1515")
        self.btn_toggle_server.config(
            text="▶  START SERVER",
            bg=self.ACCENT_BLUE,
            activebackground="#2563eb",
        )
        logging.info("Server berhasil dihentikan.")

    def on_close(self):
        if self.is_running:
            if messagebox.askyesno("Konfirmasi", "Server sedang berjalan. Apakah Anda yakin ingin mematikan server dan keluar?"):
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = ExtendDisplayServerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
