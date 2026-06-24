"""Headroom — proxy manager & dashboard."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime

# ── Bootstrap: auto-install dependencies on first run ────────────────

_REQUIRED = ["customtkinter", "pystray", "Pillow"]

def _bootstrap():
    missing = []
    for pkg in _REQUIRED:
        mod = {"Pillow": "PIL", "pystray": "pystray", "customtkinter": "customtkinter"}[pkg]
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    import tkinter as _tk

    root = _tk.Tk()
    root.title("Headroom — First-time Setup")
    root.geometry("420x220")
    root.configure(bg="#1e1e2e")
    root.resizable(False, False)

    _tk.Label(root, text="Setting up Headroom...",
              font=("Segoe UI", 14, "bold"),
              bg="#1e1e2e", fg="#cdd6f4").pack(pady=(28, 8))

    status_var = _tk.StringVar(value=f"Installing {', '.join(missing)}...")
    _tk.Label(root, textvariable=status_var,
              font=("Segoe UI", 10),
              bg="#1e1e2e", fg="#a6adc8").pack(pady=4)

    progress_var = _tk.StringVar(value="")
    _tk.Label(root, textvariable=progress_var,
              font=("Segoe UI", 9),
              bg="#1e1e2e", fg="#6c7086").pack(pady=4)

    install_ok = []

    def _install():
        failed = []
        for i, pkg in enumerate(missing):
            root.after(0, lambda p=pkg: status_var.set(f"Installing {p}..."))
            root.after(0, lambda i=i: progress_var.set(
                f"({i+1}/{len(missing)})"))
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, timeout=180,
                )
                if result.returncode != 0:
                    failed.append(pkg)
            except Exception:
                failed.append(pkg)

        if failed:
            root.after(0, lambda: status_var.set(
                f"Failed: {', '.join(failed)}"))
            root.after(0, lambda: progress_var.set(
                "Close this window and run:\n"
                f"  pip install {' '.join(failed)}"))
        else:
            install_ok.append(True)
            root.after(0, lambda: status_var.set("Done! Restarting..."))
            root.after(800, root.destroy)

    threading.Thread(target=_install, daemon=True).start()
    root.mainloop()

    if not install_ok:
        sys.exit(1)

    os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

# ── Now safe to import ───────────────────────────────────────────────

import customtkinter as ctk

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Platform ─────────────────────────────────────────────────────────

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# ── Config ───────────────────────────────────────────────────────────

PROXY_PORT = 8787
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"
REFRESH_MS = 3000

def _get_appdata():
    if IS_WIN:
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "headroom-app")
    if IS_MAC:
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "headroom-app")
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(xdg, "headroom-app")

_APPDATA = _get_appdata()
CONFIG_PATH = os.path.join(_APPDATA, "config.json")
PID_PATH = os.path.join(_APPDATA, "proxy.pid")


def _find_headroom_exe():
    """Auto-detect headroom executable."""
    from_env = os.environ.get("HEADROOM_EXE")
    if from_env and os.path.isfile(from_env):
        return from_env

    import shutil

    if IS_WIN:
        # Check Python Scripts directories
        for base in sys.path:
            scripts = os.path.join(os.path.dirname(base), "Scripts", "headroom.exe")
            if os.path.isfile(scripts):
                return scripts
        found = shutil.which("headroom.exe")
        if found and found.lower().endswith(".exe"):
            return found
        candidates = [
            os.path.join(sys.prefix, "Scripts", "headroom.exe"),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                         "Python", "Scripts", "headroom.exe"),
        ]
    else:
        found = shutil.which("headroom")
        if found:
            return found
        candidates = [
            os.path.join(sys.prefix, "bin", "headroom"),
            os.path.join(os.path.expanduser("~"), ".local", "bin", "headroom"),
        ]

    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


HEADROOM_EXE = _find_headroom_exe()

# ── Platform helpers ─────────────────────────────────────────────────

def _popen_kwargs():
    if IS_WIN:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

def _kill_pid(pid):
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, **_popen_kwargs())
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

def _kill_by_name():
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/IM", "headroom.exe"],
                       capture_output=True, **_popen_kwargs())
    else:
        subprocess.run(["pkill", "-f", "headroom.*proxy"],
                       capture_output=True)

def _set_env_persistent(key, value):
    """Set user-level env var that persists across sessions."""
    os.environ[key] = value
    if IS_WIN:
        subprocess.run(["setx", key, value],
                       capture_output=True, **_popen_kwargs())
    elif IS_MAC:
        _write_shell_export(key, value)
    else:
        _write_shell_export(key, value)

def _unset_env_persistent(key):
    """Remove user-level env var."""
    os.environ.pop(key, None)
    if IS_WIN:
        subprocess.run(["setx", key, ""],
                       capture_output=True, **_popen_kwargs())
        subprocess.run(["reg", "delete", r"HKCU\Environment",
                        "/v", key, "/f"],
                       capture_output=True, **_popen_kwargs())
    else:
        _remove_shell_export(key)

def _write_shell_export(key, value):
    """Append export to ~/.bashrc and ~/.zshrc if not already present."""
    line = f'export {key}="{value}"'
    for rc in [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]:
        if os.path.isfile(rc):
            content = open(rc).read()
            if line not in content:
                with open(rc, "a") as f:
                    f.write(f"\n# Added by Headroom Dashboard\n{line}\n")

def _remove_shell_export(key):
    """Remove export lines from shell rc files."""
    for rc in [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]:
        if os.path.isfile(rc):
            lines = open(rc).readlines()
            with open(rc, "w") as f:
                skip_next = False
                for ln in lines:
                    if f"export {key}=" in ln:
                        skip_next = False
                        continue
                    if ln.strip() == "# Added by Headroom Dashboard":
                        skip_next = True
                        continue
                    if skip_next:
                        skip_next = False
                        continue
                    f.write(ln)

def _open_in_explorer(filepath):
    filepath = os.path.abspath(filepath)
    folder = os.path.dirname(filepath) if os.path.isfile(filepath) else filepath
    if IS_WIN:
        if os.path.isfile(filepath):
            subprocess.Popen(["explorer", "/select,", filepath])
        else:
            subprocess.Popen(["explorer", folder])
    elif IS_MAC:
        subprocess.Popen(["open", "-R" if os.path.isfile(filepath) else "", folder])
    else:
        subprocess.Popen(["xdg-open", folder])

PROXY_OPTIONS = [
    ("code_aware",  "Code-Aware",  "AST-based code compression",                True),
    ("code_graph",  "Code-Graph",  "Index codebase for smarter compression",    False),
    ("memory",      "Memory",      "Persistent memory across sessions",         False),
    ("learn",       "Learn",       "Learn from traffic patterns",               False),
    ("optimize",    "Optimize",    "Enable compression optimization",           True),
    ("cache",       "Cache",       "Semantic caching",                          True),
    ("rate_limit",  "Rate Limit",  "Rate limiting protection",                  True),
    ("kompress",    "Kompress",    "ML compression engine",                     True),
]

def _ensure_appdata():
    os.makedirs(_APPDATA, exist_ok=True)

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
            defaults = {key: default for key, _, _, default in PROXY_OPTIONS}
            defaults.update(saved)
            return defaults
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {key: default for key, _, _, default in PROXY_OPTIONS}

def save_config(cfg):
    try:
        _ensure_appdata()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass

def save_pid(pid):
    try:
        _ensure_appdata()
        with open(PID_PATH, "w") as f:
            f.write(str(pid))
    except OSError:
        pass

def load_pid():
    try:
        with open(PID_PATH, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None

def clear_pid():
    try:
        os.remove(PID_PATH)
    except OSError:
        pass

def build_proxy_args(cfg, exe=None):
    args = [exe or HEADROOM_EXE, "proxy", "--no-telemetry", "--port", str(PROXY_PORT)]
    if cfg.get("code_aware", True):
        args.append("--code-aware")
    else:
        args.append("--no-code-aware")
    if cfg.get("code_graph", False):
        args.append("--code-graph")
    if cfg.get("memory", False):
        args.append("--memory")
    if cfg.get("learn", False):
        args.append("--learn")
    if not cfg.get("optimize", True):
        args.append("--no-optimize")
    if not cfg.get("cache", True):
        args.append("--no-cache")
    if not cfg.get("rate_limit", True):
        args.append("--no-rate-limit")
    if not cfg.get("kompress", True):
        args.append("--disable-kompress")
    return args

# ── Helpers ──────────────────────────────────────────────────────────

def fmt_tokens(n):
    if not n: return "0"
    n = float(n)
    if n >= 1_000_000: return f"{n / 1_000_000:.1f}M"
    if n >= 1_000: return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"

def fmt_duration(sec):
    if not sec or sec <= 0: return "—"
    sec = float(sec)
    if sec >= 86400:
        return f"{int(sec // 86400)}d {int((sec % 86400) // 3600)}h"
    if sec >= 3600:
        return f"{int(sec // 3600)}h {int((sec % 3600) // 60)}m"
    if sec >= 60:
        return f"{int(sec // 60)}m {int(sec % 60)}s"
    return f"{sec:.0f}s"

def fmt_usd(v):
    if not v: return "$0.00"
    v = float(v)
    if v >= 1: return f"${v:.2f}"
    if v >= 0.01: return f"${v:.3f}"
    if v > 0: return f"${v:.4f}"
    return "$0.00"

def deep(d, *keys, fallback=None):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return fallback
    return d if d is not None else fallback

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect blocked", headers, fp)

_opener = urllib.request.build_opener(_NoRedirect)

def fetch_json(path):
    try:
        url = f"{PROXY_URL}{path}"
        req = urllib.request.Request(url)
        with _opener.open(req, timeout=2) as r:
            data = r.read(1 * 1024 * 1024)  # cap at 1MB
            return json.loads(data)
    except Exception:
        return None


# ── Accent colors ────────────────────────────────────────────────────

GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
RED = "#f38ba8"
DIM = "#6c7086"
SUBTEXT = "#a6adc8"
SURFACE2 = "#45475a"
ALERT_THRESHOLD = 80  # percent


def _make_tray_icon(color="#a6e3a1"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=14, fill=color)
    draw.text((16, 14), "H", fill="white",
              font=None)  # fallback bitmap font
    return img


# ── App ──────────────────────────────────────────────────────────────

class HeadroomApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Headroom")
        self.geometry("780x560")
        self.minsize(680, 480)

        self._health = None
        self._stats = None
        self._running = False
        self._busy = False
        self._switch_updating = False
        self._alert_shown = False
        self._tray_icon = None
        self._tray_notified = False
        self._fetch_lock = threading.Lock()
        self._refresh_id = None
        self._proxy_proc = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Ensure config file exists on first launch
        if not os.path.isfile(CONFIG_PATH):
            save_config(load_config())

        self._build_sidebar()
        self._build_main()
        self._build_alert_bar()

        if HAS_TRAY:
            self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        else:
            self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._refresh()

    def _on_close(self):
        self._cleanup_tray()
        self.destroy()

    def _cleanup_tray(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    # ── Sidebar ──────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=172, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_rowconfigure(10, weight=1)
        sb.grid_propagate(False)

        ctk.CTkLabel(sb, text="headroom",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")

        ctk.CTkLabel(sb, text="proxy manager",
                     font=ctk.CTkFont(size=11), text_color=DIM
                     ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        # Switch
        self._proxy_var = ctk.StringVar(value="off")
        self._switch = ctk.CTkSwitch(
            sb, text="Proxy", variable=self._proxy_var,
            onvalue="on", offvalue="off",
            command=self._on_switch,
            font=ctk.CTkFont(size=13),
            progress_color=GREEN,
        )
        self._switch.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="w")

        # Info
        self._sb_version = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=11), text_color=DIM)
        self._sb_version.grid(row=3, column=0, padx=20, sticky="w")
        self._sb_uptime = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=11), text_color=DIM)
        self._sb_uptime.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="w")

        # Services heading
        ctk.CTkLabel(sb, text="Services",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=DIM
                     ).grid(row=5, column=0, padx=20, pady=(0, 4), sticky="w")

        self._svc_frame = ctk.CTkFrame(sb, fg_color="transparent")
        self._svc_frame.grid(row=6, column=0, padx=16, sticky="nw")
        self._svc_labels = {}

        # Spacer
        spacer = ctk.CTkFrame(sb, fg_color="transparent", height=0)
        spacer.grid(row=10, column=0, sticky="nsew")

        # Timestamp
        self._sb_time = ctk.CTkLabel(sb, text="", font=ctk.CTkFont(size=10), text_color=DIM)
        self._sb_time.grid(row=11, column=0, padx=20, pady=(0, 16), sticky="sw")

    # ── Main area ────────────────────────────────────────────────────

    def _build_main(self):
        main = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 0), pady=(0, 0))
        main.grid_columnconfigure(0, weight=1)
        self._main = main

        # ── Usage bars ──
        usage = ctk.CTkFrame(main, corner_radius=12)
        usage.pack(fill="x", padx=16, pady=(16, 8))
        usage.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(usage, text="Usage",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=0, column=0, columnspan=4, padx=16, pady=(12, 8), sticky="w")

        self._bar_5h, self._lbl_5h, self._lbl_5h_reset = self._usage_row(usage, "5-hour", 1)
        self._bar_7d, self._lbl_7d, self._lbl_7d_reset = self._usage_row(usage, "7-day", 2)
        self._bar_extra, self._lbl_extra, self._lbl_extra_info = self._usage_row(usage, "extra", 3)

        # bottom padding
        ctk.CTkFrame(usage, height=4, fg_color="transparent").grid(row=4, column=0, columnspan=4)

        # ── Savings hero ──
        hero = ctk.CTkFrame(main, corner_radius=12)
        hero.pack(fill="x", padx=16, pady=8)
        hero.grid_columnconfigure((0, 1, 2), weight=1)

        self._hero_tokens = self._hero_stat(hero, "0", "tokens saved", 0)
        self._hero_rate = self._hero_stat(hero, "0%", "savings rate", 1)
        self._hero_cost = self._hero_stat(hero, "$0.00", "cost saved", 2)

        # ── Tabs ──
        tabs = ctk.CTkTabview(main, corner_radius=10, height=220)
        tabs.pack(fill="x", padx=16, pady=8)
        self._tabs = tabs

        # Requests tab
        t_req = tabs.add("Requests")
        t_req.grid_columnconfigure(1, weight=1)
        self._req_total = self._detail_row(t_req, "Total", 0)
        self._req_cached = self._detail_row(t_req, "Cached", 1)
        self._req_limited = self._detail_row(t_req, "Rate limited", 2)
        self._req_failed = self._detail_row(t_req, "Failed", 3)

        # Performance tab
        t_perf = tabs.add("Performance")
        t_perf.grid_columnconfigure(1, weight=1)
        self._perf_ttfb = self._detail_row(t_perf, "TTFB avg", 0)
        self._perf_range = self._detail_row(t_perf, "TTFB range", 1)
        self._perf_overhead = self._detail_row(t_perf, "Overhead", 2)
        self._perf_latency = self._detail_row(t_perf, "Latency", 3)

        # Tokens tab
        t_tok = tabs.add("Tokens")
        t_tok.grid_columnconfigure(1, weight=1)
        self._tok_input = self._detail_row(t_tok, "Input", 0)
        self._tok_output = self._detail_row(t_tok, "Output", 1)
        self._tok_saved = self._detail_row(t_tok, "Saved", 2)
        self._tok_compression = self._detail_row(t_tok, "Compression", 3)
        self._tok_cli = self._detail_row(t_tok, "CLI filtering", 4)

        # Lifetime tab
        t_lt = tabs.add("Lifetime")
        t_lt.grid_columnconfigure(1, weight=1)
        self._lt_reqs = self._detail_row(t_lt, "Requests", 0)
        self._lt_tokens = self._detail_row(t_lt, "Tokens saved", 1)
        self._lt_cost = self._detail_row(t_lt, "Savings", 2)
        self._lt_session_reqs = self._detail_row(t_lt, "Session requests", 3)
        self._lt_session_saved = self._detail_row(t_lt, "Session saved", 4)

        # Window tokens tab
        t_win = tabs.add("Window")
        t_win.grid_columnconfigure(1, weight=1)
        self._win_input = self._detail_row(t_win, "Input", 0)
        self._win_output = self._detail_row(t_win, "Output", 1)
        self._win_cache_read = self._detail_row(t_win, "Cache reads", 2)
        self._win_cache_write = self._detail_row(t_win, "Cache writes", 3)
        self._win_total = self._detail_row(t_win, "Total", 4)
        self._win_model_frame = ctk.CTkFrame(t_win, fg_color="transparent")
        self._win_model_frame.grid(row=5, column=0, columnspan=2,
                                    padx=12, pady=(8, 4), sticky="w")
        self._win_model_labels = {}

        # Config tab — interactive switches
        t_cfg = tabs.add("Config")
        t_cfg.grid_columnconfigure(0, weight=1)

        self._cfg_backend_label = ctk.CTkLabel(
            t_cfg, text="Backend: —",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        self._cfg_backend_label.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        restart_row = ctk.CTkFrame(t_cfg, fg_color="transparent")
        restart_row.grid(row=1, column=0, padx=12, sticky="ew")
        restart_row.grid_columnconfigure(0, weight=1)

        self._cfg_restart_label = ctk.CTkLabel(
            restart_row, text="", font=ctk.CTkFont(size=10), text_color=YELLOW, anchor="w")
        self._cfg_restart_label.grid(row=0, column=0, sticky="w")

        self._cfg_restart_btn = ctk.CTkButton(
            restart_row, text="Apply & Restart", width=110, height=26,
            font=ctk.CTkFont(size=11), fg_color=YELLOW, text_color="#1e1e2e",
            hover_color="#e0d090", command=self._restart_proxy)
        self._cfg_restart_btn.grid(row=0, column=1, sticky="e")
        self._cfg_restart_btn.grid_remove()  # hidden until needed

        cfg_scroll = ctk.CTkScrollableFrame(t_cfg, fg_color="transparent", height=130)
        cfg_scroll.grid(row=2, column=0, padx=4, pady=4, sticky="nsew")
        cfg_scroll.grid_columnconfigure(0, weight=1)
        t_cfg.grid_rowconfigure(2, weight=1)

        saved_cfg = load_config()
        self._option_vars = {}
        for i, (key, label, desc, default) in enumerate(PROXY_OPTIONS):
            row_frame = ctk.CTkFrame(cfg_scroll, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
            row_frame.grid_columnconfigure(0, weight=1)

            var = ctk.StringVar(value="on" if saved_cfg.get(key, default) else "off")
            self._option_vars[key] = var

            ctk.CTkLabel(row_frame, text=label,
                         font=ctk.CTkFont(size=12), anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(row_frame, text=desc,
                         font=ctk.CTkFont(size=9), text_color=DIM, anchor="w"
                         ).grid(row=1, column=0, sticky="w")

            sw = ctk.CTkSwitch(
                row_frame, text="", variable=var,
                onvalue="on", offvalue="off", width=40,
                command=lambda k=key: self._on_option_toggle(k),
                progress_color=GREEN,
            )
            sw.grid(row=0, column=1, rowspan=2, padx=(8, 4), sticky="e")

        # ── Setup tab ──
        t_setup = tabs.add("Setup")
        t_setup.grid_columnconfigure(0, weight=1)

        self._setup_status = ctk.CTkLabel(
            t_setup, text="", font=ctk.CTkFont(size=10), text_color=DIM, anchor="w")
        self._setup_status.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        setup_scroll = ctk.CTkScrollableFrame(t_setup, fg_color="transparent", height=100)
        setup_scroll.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")
        setup_scroll.grid_columnconfigure(0, weight=1)
        t_setup.grid_rowconfigure(1, weight=1)

        self._dep_rows = {}
        for i, (pkg, desc) in enumerate([
            ("headroom-ai[all]", "Headroom proxy engine (all features)"),
            ("customtkinter", "Modern UI framework"),
            ("pystray", "System tray support"),
            ("Pillow", "Image support for tray icon"),
        ]):
            row_f = ctk.CTkFrame(setup_scroll, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row_f.grid_columnconfigure(0, weight=1)

            status_lbl = ctk.CTkLabel(row_f, text="●", font=ctk.CTkFont(size=10),
                                       text_color=DIM, width=16)
            status_lbl.grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(row_f, text=pkg, font=ctk.CTkFont(size=12, weight="bold"),
                         anchor="w").grid(row=0, column=1, sticky="w", padx=(4, 0))
            ctk.CTkLabel(row_f, text=desc, font=ctk.CTkFont(size=9),
                         text_color=DIM, anchor="w"
                         ).grid(row=1, column=1, sticky="w", padx=(4, 0))

            btn = ctk.CTkButton(
                row_f, text="Install", width=70, height=24,
                font=ctk.CTkFont(size=10),
                command=lambda p=pkg: self._install_package(p),
            )
            btn.grid(row=0, column=2, rowspan=2, padx=(8, 4), sticky="e")

            self._dep_rows[pkg] = {"status": status_lbl, "btn": btn}

        self._check_deps()

        # File location buttons
        files_frame = ctk.CTkFrame(t_cfg, fg_color="transparent")
        files_frame.grid(row=3, column=0, padx=12, pady=(4, 8), sticky="ew")

        ctk.CTkButton(
            files_frame, text="📁 Config file", width=120, height=26,
            font=ctk.CTkFont(size=11), fg_color="transparent",
            border_width=1, border_color=DIM, text_color=SUBTEXT,
            hover_color=SURFACE2,
            command=lambda: self._open_file_location(CONFIG_PATH),
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            files_frame, text="📁 App folder", width=120, height=26,
            font=ctk.CTkFont(size=11), fg_color="transparent",
            border_width=1, border_color=DIM, text_color=SUBTEXT,
            hover_color=SURFACE2,
            command=lambda: self._open_file_location(
                os.path.abspath(__file__)),
        ).pack(side="left")

    # ── Alert bar ─────────────────────────────────────────────────────

    def _build_alert_bar(self):
        self._alert_frame = ctk.CTkFrame(self, corner_radius=0, height=36,
                                          fg_color="#45273a")
        self._alert_label = ctk.CTkLabel(
            self._alert_frame,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=RED,
        )
        self._alert_label.pack(padx=16, pady=6, side="left")
        # hidden initially — we call .grid() to show

    # ── Widget factories ─────────────────────────────────────────────

    def _usage_row(self, parent, label, row):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12),
                     text_color=DIM, width=52, anchor="w"
                     ).grid(row=row, column=0, padx=(16, 8), pady=4, sticky="w")

        bar = ctk.CTkProgressBar(parent, height=12, corner_radius=6,
                                  progress_color=GREEN)
        bar.set(0)
        bar.grid(row=row, column=1, padx=(0, 8), pady=4, sticky="ew")

        pct = ctk.CTkLabel(parent, text="0%", font=ctk.CTkFont(size=12, weight="bold"),
                           width=52, anchor="e")
        pct.grid(row=row, column=2, padx=(0, 4), pady=4)

        info = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=10),
                            text_color=DIM, width=80, anchor="e")
        info.grid(row=row, column=3, padx=(0, 16), pady=4)

        return bar, pct, info

    def _hero_stat(self, parent, value, label, col):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, padx=16, pady=(16, 12), sticky="nsew")

        val = ctk.CTkLabel(f, text=value,
                           font=ctk.CTkFont(size=26, weight="bold"),
                           text_color=GREEN)
        val.pack(anchor="center")

        lbl = ctk.CTkLabel(f, text=label,
                           font=ctk.CTkFont(size=11), text_color=DIM)
        lbl.pack(anchor="center")

        return val

    def _detail_row(self, parent, label, row):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12),
                     text_color=DIM, anchor="w"
                     ).grid(row=row, column=0, padx=(12, 8), pady=5, sticky="w")

        val = ctk.CTkLabel(parent, text="—", font=ctk.CTkFont(size=12, weight="bold"),
                           anchor="e")
        val.grid(row=row, column=1, padx=(8, 16), pady=5, sticky="e")
        return val

    # ── Proxy control ────────────────────────────────────────────────

    def _on_switch(self):
        if self._busy or self._switch_updating:
            return
        self._busy = True
        if self._proxy_var.get() == "on":
            threading.Thread(target=self._do_start, daemon=True).start()
        else:
            threading.Thread(target=self._do_stop, daemon=True).start()

    def _show_error(self, msg):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Headroom — Error")
        dialog.geometry("420x180")
        dialog.resizable(False, False)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=msg, font=ctk.CTkFont(size=12),
                     wraplength=380, justify="left").pack(padx=20, pady=(20, 10))
        ctk.CTkButton(dialog, text="OK", width=80,
                      command=dialog.destroy).pack(pady=(0, 16))

    def _do_start(self):
        try:
            exe = HEADROOM_EXE
            if not exe or not os.path.isfile(exe):
                name = "headroom.exe" if IS_WIN else "headroom"
                self.after(0, lambda: self._show_error(
                    f"{name} not found.\n\n"
                    "Install:  pip install headroom-ai\n"
                    "Or set the HEADROOM_EXE environment variable."))
                return

            cfg = load_config()
            args = build_proxy_args(cfg)
            proc = subprocess.Popen(args, **_popen_kwargs())
            self._proxy_proc = proc
            save_pid(proc.pid)

            started = False
            for _ in range(15):
                time.sleep(1)
                h = fetch_json("/health")
                if h and h.get("status") == "healthy":
                    started = True
                    break

            if not started:
                self.after(0, lambda: self._show_error(
                    "Proxy did not become healthy within 15 seconds.\n"
                    "Check if port 8787 is already in use."))
                return

            _set_env_persistent("ANTHROPIC_BASE_URL", PROXY_URL)
        except Exception as e:
            self.after(0, lambda e=e: self._show_error(f"Failed to start proxy:\n{e}"))
        finally:
            self._busy = False
            self.after(200, self._refresh)

    def _stop_proxy_process(self):
        """Kill proxy by tracked PID first, fall back to kill by name."""
        killed = False

        pid = None
        if self._proxy_proc and self._proxy_proc.poll() is None:
            pid = self._proxy_proc.pid
        if not pid:
            pid = load_pid()

        if pid:
            try:
                _kill_pid(pid)
                killed = True
            except Exception:
                pass

        if not killed:
            _kill_by_name()

        self._proxy_proc = None
        clear_pid()

    def _do_stop(self):
        try:
            self._stop_proxy_process()
            time.sleep(1)
            _unset_env_persistent("ANTHROPIC_BASE_URL")
        finally:
            self._busy = False
            self.after(200, self._refresh)

    # ── Refresh ──────────────────────────────────────────────────────

    def _refresh(self):
        self._refresh_id = None
        threading.Thread(target=self._fetch_and_apply, daemon=True).start()

    def _fetch_and_apply(self):
        if not self._fetch_lock.acquire(blocking=False):
            self._schedule_next_refresh()
            return
        try:
            health = fetch_json("/health")
            stats = fetch_json("/stats")
            self.after(0, self._apply_data, health, stats)
        except Exception:
            self._schedule_next_refresh()
        finally:
            self._fetch_lock.release()

    def _apply_data(self, health, stats):
        self._running = bool(health and health.get("status") == "healthy")
        self._health = health
        self._stats = stats
        running = self._running

        try:
            self._update_sidebar(health, running)
            self._update_usage(stats)
            self._update_hero(stats)
            self._update_requests(stats)
            self._update_performance(stats)
            self._update_tokens(stats)
            self._update_lifetime(stats)
            self._update_window_tokens(stats)
            self._update_alert(stats)
            self._update_config(health)
        except Exception:
            pass

        self._schedule_next_refresh()

    def _schedule_next_refresh(self):
        if self._refresh_id is None:
            self._refresh_id = self.after(REFRESH_MS, self._refresh)

    # ── Sidebar updates ──────────────────────────────────────────────

    def _update_sidebar(self, health, running):
        # Switch state (without triggering callback)
        self._switch_updating = True
        if running:
            self._proxy_var.set("on")
            self._switch.select()
        else:
            self._proxy_var.set("off")
            self._switch.deselect()
        self._switch_updating = False

        if running and health:
            self._sb_version.configure(text=f"v{health.get('version', '?')}")
            self._sb_uptime.configure(
                text=f"up {fmt_duration(health.get('uptime_seconds', 0))}")
        else:
            self._sb_version.configure(text="offline")
            self._sb_uptime.configure(text="")

        self._sb_time.configure(text=datetime.now().strftime("%H:%M"))

        # Services — reuse labels to avoid flicker
        if health and "checks" in health:
            for name, info in health["checks"].items():
                st = info.get("status", "unknown")
                if st == "healthy":
                    dot, color = "●", GREEN
                elif st == "disabled":
                    dot, color = "○", DIM
                else:
                    dot, color = "●", RED

                if name in self._svc_labels:
                    self._svc_labels[name].configure(text=f"{dot} {name}", text_color=color)
                else:
                    lbl = ctk.CTkLabel(self._svc_frame, text=f"{dot} {name}",
                                       font=ctk.CTkFont(size=10), text_color=color,
                                       anchor="w")
                    lbl.pack(anchor="w", pady=1)
                    self._svc_labels[name] = lbl

    # ── Usage bars ───────────────────────────────────────────────────

    def _set_bar(self, bar, pct_lbl, info_lbl, data):
        if not data:
            bar.set(0)
            pct_lbl.configure(text="0%")
            info_lbl.configure(text="")
            bar.configure(progress_color=GREEN)
            return

        pct = float(data.get("utilization_pct", 0))
        bar.set(min(pct / 100, 1.0))
        pct_lbl.configure(text=f"{pct:.1f}%")

        reset = data.get("seconds_to_reset")
        if reset:
            info_lbl.configure(text=f"resets {fmt_duration(reset)}")
        else:
            info_lbl.configure(text="")

        if pct >= 80:
            bar.configure(progress_color=RED)
        elif pct >= 60:
            bar.configure(progress_color=YELLOW)
        else:
            bar.configure(progress_color=GREEN)

    def _update_usage(self, stats):
        sw = deep(stats, "subscription_window", "latest")
        self._set_bar(self._bar_5h, self._lbl_5h, self._lbl_5h_reset,
                      deep(sw, "five_hour") if sw else None)
        self._set_bar(self._bar_7d, self._lbl_7d, self._lbl_7d_reset,
                      deep(sw, "seven_day") if sw else None)

        extra = deep(sw, "extra_usage") if sw else None
        if extra and extra.get("is_enabled"):
            self._set_bar(self._bar_extra, self._lbl_extra, self._lbl_extra_info, extra)
            used = fmt_usd(extra.get("used_credits_usd", 0))
            limit = fmt_usd(extra.get("monthly_limit_usd")) if extra.get("monthly_limit_usd") else "∞"
            self._lbl_extra_info.configure(text=f"{used} / {limit}")
        else:
            self._set_bar(self._bar_extra, self._lbl_extra, self._lbl_extra_info, None)
            self._lbl_extra_info.configure(text="not enabled")

    # ── Hero ─────────────────────────────────────────────────────────

    def _update_hero(self, stats):
        tok = deep(stats, "tokens", fallback={})
        cost = deep(stats, "cost", fallback={})

        total_saved = tok.get("all_layers_saved") or tok.get("saved", 0)
        sav_pct = tok.get("all_layers_savings_percent") or tok.get("savings_percent", 0)
        cost_saved = cost.get("savings_usd", 0)

        self._hero_tokens.configure(text=fmt_tokens(total_saved))
        try:
            self._hero_rate.configure(text=f"{float(sav_pct):.1f}%" if sav_pct else "0%")
        except (ValueError, TypeError):
            self._hero_rate.configure(text="0%")
        self._hero_cost.configure(text=fmt_usd(cost_saved))

    # ── Tabs ─────────────────────────────────────────────────────────

    def _update_requests(self, stats):
        req = deep(stats, "requests", fallback={})
        for widget, key in ((self._req_total, "total"), (self._req_cached, "cached"),
                            (self._req_limited, "rate_limited"), (self._req_failed, "failed")):
            try:
                widget.configure(text=f"{int(req.get(key, 0)):,}")
            except (ValueError, TypeError):
                widget.configure(text="—")

    def _update_performance(self, stats):
        lat = deep(stats, "latency", fallback={})
        ttfb = deep(stats, "ttfb", fallback={})
        oh = deep(stats, "overhead", fallback={})
        try:
            if int(lat.get("total_requests", 0)) > 0:
                self._perf_ttfb.configure(text=f"{float(ttfb.get('average_ms', 0)):.0f}ms")
                self._perf_range.configure(
                    text=f"{float(ttfb.get('min_ms', 0)):.0f} – {float(ttfb.get('max_ms', 0)):.0f}ms")
                self._perf_overhead.configure(text=f"{float(oh.get('average_ms', 0)):.0f}ms")
                self._perf_latency.configure(text=f"{float(lat.get('average_ms', 0)):.0f}ms")
                return
        except (ValueError, TypeError):
            pass
        for w in (self._perf_ttfb, self._perf_range, self._perf_overhead, self._perf_latency):
            w.configure(text="—")

    def _update_tokens(self, stats):
        tok = deep(stats, "tokens", fallback={})
        self._tok_input.configure(text=fmt_tokens(tok.get("input", 0)))
        self._tok_output.configure(text=fmt_tokens(tok.get("output", 0)))

        saved = tok.get("all_layers_saved") or tok.get("saved", 0)
        self._tok_saved.configure(text=fmt_tokens(saved))
        self._tok_compression.configure(text=fmt_tokens(tok.get("proxy_compression_saved", 0)))
        self._tok_cli.configure(text=fmt_tokens(tok.get("cli_filtering_saved", 0)))

    def _update_lifetime(self, stats):
        ps = deep(stats, "persistent_savings", "lifetime", fallback={})
        ds = deep(stats, "display_session", fallback={})

        if ps.get("requests", 0) > 0:
            self._lt_reqs.configure(text=f"{int(ps['requests']):,}")
            self._lt_tokens.configure(text=fmt_tokens(ps.get("tokens_saved", 0)))
            self._lt_cost.configure(text=fmt_usd(ps.get("compression_savings_usd", 0)))
        else:
            for w in (self._lt_reqs, self._lt_tokens, self._lt_cost):
                w.configure(text="—")

        if ds.get("requests", 0) > 0:
            self._lt_session_reqs.configure(text=f"{int(ds['requests']):,}")
            self._lt_session_saved.configure(text=fmt_tokens(ds.get("tokens_saved", 0)))
        else:
            self._lt_session_reqs.configure(text="—")
            self._lt_session_saved.configure(text="—")

    def _update_window_tokens(self, stats):
        wt = deep(stats, "subscription_window", "latest", "window_tokens", fallback={})
        if not wt or not wt.get("total_raw"):
            for w in (self._win_input, self._win_output, self._win_cache_read,
                      self._win_cache_write, self._win_total):
                w.configure(text="—")
            return

        self._win_input.configure(text=fmt_tokens(wt.get("input", 0)))
        self._win_output.configure(text=fmt_tokens(wt.get("output", 0)))
        self._win_cache_read.configure(text=fmt_tokens(wt.get("cache_reads", 0)))
        self._win_cache_write.configure(text=fmt_tokens(wt.get("cache_writes_total", 0)))
        self._win_total.configure(text=fmt_tokens(wt.get("total_raw", 0)))

        by_model = wt.get("by_model", {})
        for name, data in by_model.items():
            total = (data.get("input", 0) + data.get("output", 0) +
                     data.get("cache_reads", 0) + data.get("cache_writes_total", 0))
            text = f"{name}: {fmt_tokens(total)}"
            if name in self._win_model_labels:
                self._win_model_labels[name].configure(text=text)
            else:
                lbl = ctk.CTkLabel(self._win_model_frame, text=text,
                                   font=ctk.CTkFont(size=11), text_color=DIM,
                                   anchor="w")
                lbl.pack(anchor="w", pady=1)
                self._win_model_labels[name] = lbl

    def _update_alert(self, stats):
        five = deep(stats, "subscription_window", "latest", "five_hour", fallback={})
        try:
            pct = float(five.get("utilization_pct", 0)) if five else 0
            reset = float(five.get("seconds_to_reset", 0)) if five else 0
        except (ValueError, TypeError):
            pct, reset = 0, 0

        if pct >= ALERT_THRESHOLD:
            msg = f"  ⚠  5-hour usage at {pct:.0f}% — resets in {fmt_duration(reset)}"
            self._alert_label.configure(text=msg)
            if not self._alert_shown:
                self._alert_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
                self._alert_shown = True

            if HAS_TRAY and self._tray_icon and not self._tray_notified:
                try:
                    self._tray_icon.notify(
                        f"5-hour usage at {pct:.0f}%",
                        "Headroom — Rate Limit Warning")
                    self._tray_notified = True
                except Exception:
                    pass
        else:
            if self._alert_shown:
                self._alert_frame.grid_forget()
                self._alert_shown = False
            self._tray_notified = False

    # ── System tray ──────────────────────────────────────────────────

    def _minimize_to_tray(self):
        if not HAS_TRAY:
            self.destroy()
            return

        self.withdraw()

        if self._tray_icon is None:
            icon_img = _make_tray_icon()
            menu = pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            )
            self._tray_icon = pystray.Icon("headroom", icon_img,
                                            "Headroom", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _tray_show(self, icon=None, item=None):
        self.after(0, self._do_show)

    def _do_show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_quit(self, icon=None, item=None):
        self._cleanup_tray()
        self.after(0, self.destroy)

    # ── Setup / Install ─────────────────────────────────────────────

    def _check_deps(self):
        from importlib.util import find_spec
        pkg_checks = {
            "headroom-ai[all]": "headroom",
            "customtkinter": "customtkinter",
            "pystray": "pystray",
            "Pillow": "PIL",
        }
        all_ok = True
        for pkg, row in self._dep_rows.items():
            mod = pkg_checks.get(pkg, pkg)
            installed = find_spec(mod) is not None
            if installed:
                row["status"].configure(text="●", text_color=GREEN)
                row["btn"].configure(text="Installed", state="disabled",
                                     fg_color="transparent", border_width=1,
                                     border_color=DIM, text_color=DIM)
            else:
                row["status"].configure(text="○", text_color=RED)
                row["btn"].configure(text="Install", state="normal",
                                     fg_color=None, border_width=0,
                                     text_color=None)
                all_ok = False

        exe = HEADROOM_EXE
        if not exe or not os.path.isfile(exe):
            row = self._dep_rows.get("headroom-ai[all]")
            if row:
                row["status"].configure(text="○", text_color=RED)
                row["btn"].configure(text="Install", state="normal",
                                     fg_color=None, border_width=0,
                                     text_color=None)
                all_ok = False

        if all_ok:
            self._setup_status.configure(text="All dependencies installed ✓",
                                          text_color=GREEN)
        else:
            self._setup_status.configure(text="Some dependencies missing",
                                          text_color=YELLOW)

    def _install_package(self, pkg):
        row = self._dep_rows[pkg]
        row["btn"].configure(text="Installing...", state="disabled")
        self._setup_status.configure(text=f"Installing {pkg}...", text_color=SUBTEXT)
        threading.Thread(target=self._do_install, args=(pkg,), daemon=True).start()

    def _do_install(self, pkg):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg],
                capture_output=True, text=True, timeout=120,
            )
            success = result.returncode == 0
            if success and "headroom-ai" in pkg:
                global HEADROOM_EXE
                HEADROOM_EXE = _find_headroom_exe()
        except Exception:
            success = False

        def _update():
            if success:
                self._setup_status.configure(
                    text=f"Installed {pkg} ✓", text_color=GREEN)
            else:
                self._setup_status.configure(
                    text=f"Failed to install {pkg}", text_color=RED)
            self._check_deps()

        self.after(0, _update)

    def _open_file_location(self, filepath):
        _open_in_explorer(filepath)

    def _on_option_toggle(self, key):
        cfg = load_config()
        cfg[key] = self._option_vars[key].get() == "on"
        save_config(cfg)

        if self._running:
            self._cfg_restart_label.configure(text="⟳ Restart proxy to apply")
            self._cfg_restart_btn.grid()
        else:
            self._cfg_restart_label.configure(text="")
            self._cfg_restart_btn.grid_remove()

    def _restart_proxy(self):
        if self._busy:
            return
        self._busy = True
        self._cfg_restart_label.configure(text="Restarting...")
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self):
        try:
            self._stop_proxy_process()
            time.sleep(1.5)

            exe = HEADROOM_EXE
            if not exe or not os.path.isfile(exe):
                name = "headroom.exe" if IS_WIN else "headroom"
                self.after(0, lambda: self._show_error(f"{name} not found."))
                return

            cfg = load_config()
            args = build_proxy_args(cfg)
            proc = subprocess.Popen(args, **_popen_kwargs())
            self._proxy_proc = proc
            save_pid(proc.pid)

            for _ in range(15):
                time.sleep(1)
                h = fetch_json("/health")
                if h and h.get("status") == "healthy":
                    break

            _set_env_persistent("ANTHROPIC_BASE_URL", PROXY_URL)
        finally:
            self._busy = False
            def _clear():
                self._cfg_restart_label.configure(text="")
                self._cfg_restart_btn.grid_remove()
            self.after(0, _clear)
            self.after(200, self._refresh)

    def _update_config(self, health):
        if not health or "config" not in health:
            self._cfg_backend_label.configure(text="Backend: —")
            return

        self._cfg_backend_label.configure(
            text=f"Backend: {health['config'].get('backend', '?')}")


if __name__ == "__main__":
    app = HeadroomApp()
    app.mainloop()
