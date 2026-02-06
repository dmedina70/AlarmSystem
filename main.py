#!/usr/bin/env python3
"""
SMT Alarm Server - Large Display Edition
Optimized for big screens - maximum tile size
"""

import csv
import datetime
import json
import logging
import queue
import socket
import threading
import time
import signal
from typing import Dict, List
from configparser import ConfigParser
import socketserver
import tkinter as tk
import pygame
import sys
from pathlib import Path
import requests

# ── Base Directory ──────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# ── File Paths ──────────────────────────────────────────────────────
CONFIG_FILE = BASE_DIR / "config_server.txt"
LINES_FILE = BASE_DIR / "lines.txt"
LOG_FILE = BASE_DIR / "alarm_requests.csv"
INIT = BASE_DIR / "config.init"
LOG_FILE_PATH = BASE_DIR / "server_debug.log"

# ── Load Init Config ────────────────────────────────────────────────
cfg = ConfigParser(interpolation=None)
cfg.read(INIT)

try:
    PORT = cfg.getint('Server', 'port')
    WEBHOOK_URL = cfg.get('Server', 'hook')
    INTERVAL = cfg.getint('Interval', 'interval')
except Exception as e:
    PORT = 9999
    WEBHOOK_URL = ""
    INTERVAL = 300
    print(f"Config warning: {e}, using defaults")

HOST = "0.0.0.0"
COLUMNS = 4

# ── Color Palette - Bright, High Visibility ─────────────────────────
COLORS = {
    "bg_dark": "#000000",

    # Bright green like your version
    "status_ok": "#00c853",
    "status_ok_pulse": "#00e064",

    # Bright red for alarms
    "status_alarm": "#ff1744",
    "status_alarm_pulse": "#ff5252",

    # Text - pure white for maximum contrast
    "text_white": "#ffffff",
    "text_black": "#000000",
    "text_muted": "#888888",
}

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("🔧 SMT Alarm Server (Large Display) started")


# ── Large Tile - Fills Maximum Space ────────────────────────────────

class LargeTile(tk.Frame):
    """
    Large tile that fills available space.
    Shows: Line Name, Alarm Type (when active), Timer (when active)
    """

    def __init__(self, parent, line_name: str, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)

        self.line_name = line_name
        self.alarm_name = ""
        self.start_time = 0.0
        self.status = "ok"
        self.pulse_state = False
        self.custom_color = None
        self.custom_color_pulse = None

        # Main container - minimal border
        self.container = tk.Frame(self, bg=COLORS["status_ok"])
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # Use grid for better vertical centering
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Content frame centered in container
        self.content = tk.Frame(self.container, bg=COLORS["status_ok"])
        self.content.grid(row=0, column=0, sticky="nsew")

        # Line name - LARGE, centered
        self.line_label = tk.Label(
            self.content,
            text=line_name,
            font=("Arial Black", 36, "bold"),
            bg=COLORS["status_ok"],
            fg=COLORS["text_white"]
        )
        self.line_label.pack(expand=True)

        # Alarm name - shown below line name when active
        self.alarm_label = tk.Label(
            self.content,
            text="",
            font=("Arial", 24, "bold"),
            bg=COLORS["status_ok"],
            fg=COLORS["text_white"]
        )
        # Initially hidden

        # Timer - shown when active
        self.timer_label = tk.Label(
            self.content,
            text="",
            font=("Consolas", 28, "bold"),
            bg=COLORS["status_ok"],
            fg=COLORS["text_white"]
        )
        # Initially hidden

    def _get_color(self) -> str:
        """Get current background color."""
        if self.status == "ok":
            return COLORS["status_ok"]
        elif self.custom_color:
            if self.pulse_state and self.custom_color_pulse:
                return self.custom_color_pulse
            return self.custom_color
        else:
            if self.pulse_state:
                return COLORS["status_alarm_pulse"]
            return COLORS["status_alarm"]

    def _get_text_color(self, bg_color: str) -> str:
        """Get contrasting text color based on background brightness."""
        bg = bg_color.lstrip("#")
        r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return COLORS["text_black"] if brightness > 128 else COLORS["text_white"]

    def _lighten(self, hex_color: str) -> str:
        """Lighten a color for pulse effect."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = min(255, int(r + (255 - r) * 0.2))
        g = min(255, int(g + (255 - g) * 0.2))
        b = min(255, int(b + (255 - b) * 0.2))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _update_colors(self):
        """Update all widget colors."""
        bg = self._get_color()
        fg = self._get_text_color(bg)

        self.container.config(bg=bg)
        self.content.config(bg=bg)
        self.line_label.config(bg=bg, fg=fg)
        self.alarm_label.config(bg=bg, fg=fg)
        self.timer_label.config(bg=bg, fg=fg)

    def set_ok(self):
        """Set tile to OK status."""
        self.status = "ok"
        self.alarm_name = ""
        self.start_time = 0.0
        self.custom_color = None
        self.custom_color_pulse = None

        # Hide alarm and timer labels
        self.alarm_label.pack_forget()
        self.timer_label.pack_forget()

        # Just show line name centered
        self.line_label.pack(expand=True)

        self._update_colors()

    def set_alarm(self, alarm_name: str, color: str = None):
        """Set tile to alarm status."""
        self.status = "alarm"
        self.alarm_name = alarm_name
        self.start_time = time.time()

        if color:
            self.custom_color = color
            self.custom_color_pulse = self._lighten(color)
        else:
            self.custom_color = None
            self.custom_color_pulse = None

        # Reorganize layout: Line name, alarm name, timer
        self.line_label.pack_forget()
        self.alarm_label.pack_forget()
        self.timer_label.pack_forget()

        self.line_label.pack(expand=True, pady=(10, 0))
        self.alarm_label.config(text=alarm_name)
        self.alarm_label.pack(pady=0)
        self.timer_label.pack(pady=(0, 10))

        self._update_colors()

    def update_timer(self):
        """Update the timer display."""
        if self.status != "ok" and self.start_time:
            elapsed = int(time.time() - self.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.timer_label.config(text=f"{h}:{m:02d}:{s:02d}")

    def toggle_pulse(self):
        """Toggle pulse state."""
        if self.status != "ok":
            self.pulse_state = not self.pulse_state
            self._update_colors()


# ── Main Application ────────────────────────────────────────────────

class AlarmServerApp:
    def __init__(self):
        self.config = self._load_alarms_config()
        self.lines = self._load_lines()
        self.alarm_colors = self._load_alarm_colors()

        self.alarm_queue = queue.Queue()
        self.gui_queue = queue.Queue()

        self.replay_tracker: Dict[tuple, float] = {}
        self.solved_alarms: set = set()
        self.active_alarms: Dict[str, tuple] = {}

        self.stats = {"queued": 0, "played": 0, "solved": 0, "errors": 0}

        pygame.mixer.init()

        self._ensure_log_header()
        self._start_alarm_worker()
        self.server = self._start_socket_server()

        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

        self._build_gui()
        self._run_gui()

    def _load_alarms_config(self) -> Dict[str, Dict[str, Path]]:
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(f"{CONFIG_FILE} not found")

        mapping = {}
        for line in CONFIG_FILE.read_text().splitlines():
            row = line.strip()
            if not row or row.startswith("#"):
                continue
            try:
                ln, name, path_str = [x.strip() for x in row.split(",")]
                path = Path(path_str)
                if path.is_file():
                    mapping.setdefault(ln, {})[name] = path
                else:
                    logging.warning("Missing alarm file: %s", path)
            except ValueError:
                continue
        return mapping

    def _load_lines(self) -> List[str]:
        if LINES_FILE.exists():
            return [l.strip() for l in LINES_FILE.read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
        return sorted(self.config.keys())

    def _load_alarm_colors(self) -> Dict[str, str]:
        color_file = BASE_DIR / "alarm_colors.txt"
        colors = {}
        if not color_file.exists():
            return colors

        for line in color_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            try:
                name, color = [x.strip() for x in line.split("=", 1)]
                colors[name] = color
            except:
                continue
        return colors

    def _ensure_log_header(self):
        if not LOG_FILE.exists():
            with LOG_FILE.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "line", "alarm", "status", "employee", "elapsed"])

    def _start_alarm_worker(self):
        threading.Thread(target=self._alarm_worker, daemon=True).start()

    def _alarm_worker(self):
        REPLAY_INTERVAL = INTERVAL

        while True:
            now = time.time()

            try:
                ln, an = self.alarm_queue.get(timeout=1)
                key = (ln, an)

                if key not in self.replay_tracker:
                    self.replay_tracker[key] = now

                ts = datetime.datetime.now().isoformat()
                path = self.config.get(ln, {}).get(an)
                status = "error:unknown"

                self.gui_queue.put(("queued", ln, an, ts))

                if path:
                    try:
                        pygame.mixer.music.load(str(path))
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.wait(100)
                        self.gui_queue.put(("finished", ln, an, ts))
                        status = "played"
                    except Exception as e:
                        logging.exception("Playback error")
                        self.gui_queue.put(("error", ln, an, ts))
                        status = f"error:{e}"
                else:
                    self.gui_queue.put(("error", ln, an, ts))

                with LOG_FILE.open("a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([ts, ln, an, status, "", ""])

                self.alarm_queue.task_done()

            except queue.Empty:
                pass

            for (ln, an), first_trigger in list(self.replay_tracker.items()):
                elapsed = now - first_trigger
                if elapsed >= REPLAY_INTERVAL and int(elapsed) % REPLAY_INTERVAL < 1:
                    if (ln, an) not in self.solved_alarms:
                        logging.info("Replaying alarm for %s • %s", ln, an)
                        self.alarm_queue.put((ln, an))

    def _send_teams_notification(self, line: str, alarm: str, event: str, details: str = ""):
        if not WEBHOOK_URL:
            return

        payload = {
            "message": f"**{event}**\n\nLine: `{line}`\nAlarm: `{alarm}`",
            "detail": details,
            "type": alarm
        }

        try:
            response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Webhook error: {e}")

    def _start_socket_server(self) -> socketserver.ThreadingTCPServer:
        app = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                raw = self.request.recv(1024).strip()
                ts = datetime.datetime.now().isoformat()

                try:
                    data = json.loads(raw.decode())
                except json.JSONDecodeError:
                    self.request.sendall(b"error:invalid json")
                    return

                ln = data.get("line", "")
                an = data.get("alarm", "")

                if data.get("solved"):
                    try:
                        self.request.sendall(b"OK")
                        self.request.shutdown(socket.SHUT_WR)
                    except Exception as e:
                        logging.warning(f"Response error: {e}")

                    threading.Thread(target=app._log_solved, args=(data, ts), daemon=True).start()
                    return

                if ln not in app.lines:
                    logging.warning("Rejected: line '%s' not allowed", ln)
                    self.request.sendall(b"error:unauthorized line")
                    return

                if an in app.config.get(ln, {}):
                    app.alarm_queue.put((ln, an))
                    self.request.sendall(b"OK")
                    app._send_teams_notification(ln, an, "Alarm Triggered")
                else:
                    self.request.sendall(b"error:unknown alarm")

        server = socketserver.ThreadingTCPServer((HOST, PORT), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logging.info("Server listening on %s:%d", HOST, PORT)
        return server

    def _log_solved(self, data: dict, timestamp: str):
        ln = data.get("line")
        an = data.get("alarm")
        emp = data.get("employee", "")
        elapsed = data.get("elapsed", 0.0)

        try:
            solved_sound = BASE_DIR / "LineSound" / "off.wav"
            if solved_sound.is_file():
                pygame.mixer.music.load(str(solved_sound))
                pygame.mixer.music.play()
        except Exception as e:
            logging.warning(f"Solved sound error: {e}")

        with LOG_FILE.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, ln, an, "solved", emp, f"{elapsed:.1f}"])

        self.gui_queue.put(("solved", ln, an, timestamp, elapsed, emp))
        self._send_teams_notification(ln, an, "Alarm Solved", f"Employee: {emp}, Time: {elapsed:.1f}s")

        self.replay_tracker.pop((ln, an), None)
        self.solved_alarms.add((ln, an))

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("SMT Alarm Monitor")
        self.root.configure(bg=COLORS["bg_dark"])

        # Fullscreen
        self.root.attributes('-fullscreen', True)
        self.root.bind('<Escape>', lambda e: self.root.attributes('-fullscreen', False))
        self.root.bind('<F11>', lambda e: self.root.attributes('-fullscreen',
                                                               not self.root.attributes('-fullscreen')))

        # ── Compact Header ──────────────────────────────────────────
        header = tk.Frame(self.root, bg=COLORS["bg_dark"], height=50)
        header.pack(fill="x", padx=10, pady=(5, 2))
        header.pack_propagate(False)

        # Left: Title + Status
        tk.Label(
            header,
            text="SMT ALARM MONITOR",
            font=("Arial Black", 20, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_white"]
        ).pack(side="left")

        self.status_label = tk.Label(
            header,
            text="",
            font=("Arial", 16, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["status_ok"]
        )
        self.status_label.pack(side="left", padx=(20, 0))

        # Right: Clock and Date
        clock_frame = tk.Frame(header, bg=COLORS["bg_dark"])
        clock_frame.pack(side="right")

        self.time_label = tk.Label(
            clock_frame,
            text="00:00:00",
            font=("Consolas", 28, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_white"]
        )
        self.time_label.pack(side="top", anchor="e")

        self.date_label = tk.Label(
            clock_frame,
            text="",
            font=("Arial", 10),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_muted"]
        )
        self.date_label.pack(side="top", anchor="e")

        # ── Tiles Grid - Maximum Space ──────────────────────────────
        self.tiles_frame = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self.tiles_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Calculate grid based on number of lines
        num_lines = len(self.lines)
        if num_lines <= 4:
            cols = num_lines
        elif num_lines <= 8:
            cols = 4
        elif num_lines <= 12:
            cols = 4
        elif num_lines <= 20:
            cols = 5
        else:
            cols = 6

        rows = (num_lines + cols - 1) // cols if num_lines > 0 else 1

        for c in range(cols):
            self.tiles_frame.columnconfigure(c, weight=1, uniform="col")
        for r in range(rows):
            self.tiles_frame.rowconfigure(r, weight=1, uniform="row")

        # Create tiles
        self.tiles: Dict[str, LargeTile] = {}

        for idx, ln in enumerate(self.lines):
            r, c = divmod(idx, cols)
            tile = LargeTile(self.tiles_frame, ln)
            tile.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            self.tiles[ln] = tile

        # ── Minimal Footer ──────────────────────────────────────────
        footer = tk.Frame(self.root, bg=COLORS["bg_dark"], height=25)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        tk.Label(
            footer,
            text=f"Server: {socket.gethostname()}:{PORT}",
            font=("Arial", 9),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=10)

        self.stats_label = tk.Label(
            footer,
            text="",
            font=("Arial", 9),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_muted"]
        )
        self.stats_label.pack(side="right", padx=10)

    def _run_gui(self):
        self._update_time()
        self._update_timers()
        self._pulse_alarms()
        self._process_gui_queue()
        self.root.mainloop()

    def _update_time(self):
        now = datetime.datetime.now()
        self.time_label.config(text=now.strftime("%H:%M:%S"))
        self.date_label.config(text=now.strftime("%A, %B %d, %Y"))
        self.root.after(1000, self._update_time)

    def _update_timers(self):
        for tile in self.tiles.values():
            tile.update_timer()

        active_count = len(self.active_alarms)
        if active_count > 0:
            self.status_label.config(
                text=f"⚠ {active_count} ALARM{'S' if active_count > 1 else ''} ACTIVE",
                fg="#ff1744"
            )
        else:
            self.status_label.config(text="", fg=COLORS["status_ok"])

        self.root.after(1000, self._update_timers)

    def _pulse_alarms(self):
        for tile in self.tiles.values():
            tile.toggle_pulse()
        self.root.after(500, self._pulse_alarms)

    def _process_gui_queue(self):
        try:
            while True:
                evt = self.gui_queue.get_nowait()
                ev = evt[0]

                if ev == "queued":
                    _, ln, an, ts = evt
                    self.stats["queued"] += 1

                    if ln in self.tiles:
                        color = self.alarm_colors.get(an)
                        self.tiles[ln].set_alarm(an, color)
                        self.active_alarms[ln] = (an, time.time())

                    self._update_stats()

                elif ev == "finished":
                    _, ln, an, ts = evt
                    self.stats["played"] += 1
                    self._update_stats()

                elif ev == "error":
                    _, ln, an, ts = evt
                    self.stats["errors"] += 1
                    self._update_stats()

                elif ev == "solved":
                    _, ln, an, ts, elapsed, emp = evt
                    self.stats["solved"] += 1

                    if ln in self.tiles:
                        self.tiles[ln].set_ok()

                    self.active_alarms.pop(ln, None)
                    self._update_stats()

        except queue.Empty:
            pass

        self.root.after(100, self._process_gui_queue)

    def _update_stats(self):
        self.stats_label.config(
            text=f"Queued: {self.stats['queued']} | Played: {self.stats['played']} | Solved: {self.stats['solved']}"
        )

    def _graceful_shutdown(self, *args):
        logging.info("Shutting down...")
        self.server.shutdown()
        pygame.quit()
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    AlarmServerApp()