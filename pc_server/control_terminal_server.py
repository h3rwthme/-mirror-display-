import ctypes
import json
import logging
import os
import socket
import subprocess
import threading
import time
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Button, Controller as MouseController

from config import HOST_BIND, PORT_CONTROL
from display_streamer import VirtualMonitorGeometry

logger = logging.getLogger("ControlTerminalServer")

SPECIAL_KEY_MAP = {
    "enter": Key.enter,
    "backspace": Key.backspace,
    "tab": Key.tab,
    "esc": Key.esc,
    "space": Key.space,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "delete": Key.delete,
    "home": Key.home,
    "end": Key.end,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "shift": Key.shift,
    "win": Key.cmd,
}


class InteractiveShellSession:
    """
    Membuka sesi terminal interaktif dua arah (PowerShell / CMD) dan melakukan
    piping stdin/stdout/stderr secara real-time melalui Socket 2.
    """

    def __init__(self, send_json_callback, shell_cmd: str = "powershell.exe"):
        self.send_json = send_json_callback
        self._stop_event = threading.Event()
        cmd = [shell_cmd, "-NoLogo", "-NoExit"] if "powershell" in shell_cmd.lower() else [shell_cmd]

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )

        threading.Thread(
            target=self._pipe_reader,
            args=(self.proc.stdout, "stdout"),
            name="ShellStdoutReader",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._pipe_reader,
            args=(self.proc.stderr, "stderr"),
            name="ShellStderrReader",
            daemon=True,
        ).start()

    def _pipe_reader(self, pipe, stream_name: str):
        try:
            while not self._stop_event.is_set() and self.proc.poll() is None:
                chunk = os.read(pipe.fileno(), 1024)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                self.send_json({
                    "type": "term_out",
                    "stream": stream_name,
                    "data": text,
                })
        except (OSError, ValueError):
            pass

    def write_input(self, command_text: str):
        if self.proc.poll() is None and self.proc.stdin:
            if not command_text.endswith("\n"):
                command_text += "\r\n"
            self.proc.stdin.write(command_text.encode("utf-8", errors="replace"))
            self.proc.stdin.flush()

    def close(self):
        self._stop_event.set()
        if self.proc.poll() is None:
            self.proc.terminate()


class ControlAndTerminalServer:
    """
    Socket 2 (PORT 5002):
    - Menerima koordinat X/Y sentuhan tablet untuk simulasi Mouse (klik, drag, scroll)
      yang dipetakan langsung ke monitor virtual IddSampleDriver.
    - Menerima event Keyboard dari tablet.
    - Menyediakan jalur pipa dua arah (stdin/stdout) untuk Terminal PowerShell/CMD PC.
    """

    def __init__(self, geometry: VirtualMonitorGeometry, port: int = PORT_CONTROL):
        self.geometry = geometry
        self.port = port
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self._stop_event = threading.Event()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="ControlServerThread", daemon=True)
        thread.start()
        return thread

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((HOST_BIND, self.port))
            server_sock.listen(2)
            logger.info(f"[Socket 2 - Control & Terminal] Mendengarkan pada {HOST_BIND}:{self.port}")

            while not self._stop_event.is_set():
                try:
                    client_sock, addr = server_sock.accept()
                except OSError:
                    break
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    name=f"ControlClient-{addr[0]}",
                    daemon=True,
                ).start()

    def _handle_client(self, client_sock: socket.socket, addr: tuple[str, int]):
        peer_ip = addr[0]
        # Matikan Nagle's Algorithm untuk respons sentuhan & ketikan terminal < 1ms
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        send_lock = threading.Lock()

        def send_json(payload: dict):
            line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            with send_lock:
                try:
                    client_sock.sendall(line)
                except OSError:
                    pass

        logger.info(f"[Socket 2 - Control & Terminal] Client {peer_ip} terhubung.")
        shell_session = InteractiveShellSession(send_json_callback=send_json)

        try:
            with client_sock.makefile("r", encoding="utf-8", errors="replace") as reader:
                for raw_line in reader:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._dispatch_message(msg, shell_session, send_json)
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.info(f"[Socket 2 - Control & Terminal] Client {peer_ip} terputus ({exc})")
        finally:
            shell_session.close()
            try:
                client_sock.close()
            except OSError:
                pass

    def _dispatch_message(self, msg: dict, shell_session: InteractiveShellSession, send_json):
        msg_type = msg.get("type")

        if msg_type == "mouse":
            # Koordinat ternormalisasi (0.0 s/d 1.0) dari layar tablet
            norm_x = float(msg.get("x", 0.0))
            norm_y = float(msg.get("y", 0.0))
            action = msg.get("action", "move")

            abs_x, abs_y = self.geometry.map_normalized_to_desktop(norm_x, norm_y)
            # Gunakan Win32 SetCursorPos langsung untuk pergerakan instan tanpa interpolasi
            ctypes.windll.user32.SetCursorPos(abs_x, abs_y)

            if action == "down":
                self.mouse.press(Button.left)
            elif action == "up":
                self.mouse.release(Button.left)
            elif action == "click":
                self.mouse.click(Button.left, 1)
            elif action == "double_click":
                self.mouse.click(Button.left, 2)
            elif action == "right_click":
                self.mouse.click(Button.right, 1)
            elif action == "scroll":
                dy = int(msg.get("dy", 0))
                self.mouse.scroll(0, dy)

        elif msg_type == "key":
            action = msg.get("action", "press")
            key_name = str(msg.get("key", "")).lower()
            text = msg.get("text", "")

            if action == "text" and text:
                self.keyboard.type(text)
            else:
                target_key = SPECIAL_KEY_MAP.get(key_name, key_name[:1] if key_name else None)
                if target_key:
                    if action == "down":
                        self.keyboard.press(target_key)
                    elif action == "up":
                        self.keyboard.release(target_key)
                    else:
                        self.keyboard.press(target_key)
                        self.keyboard.release(target_key)

        elif msg_type == "term_in":
            cmd_data = str(msg.get("data", ""))
            shell_session.write_input(cmd_data)

        elif msg_type == "ping":
            send_json({
                "type": "pong",
                "client_ts": msg.get("client_ts", 0),
                "server_ts": int(time.time() * 1000),
            })

    def stop(self):
        self._stop_event.set()
