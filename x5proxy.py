#!/usr/bin/env python3
"""
IPNET - one-click USA proxy.
Single EXE distributed via GitHub Releases.

Each launch shows the same simple window:
  1. Paste your proxy repo link (public, or private + token below).
  2. Press Start.
The app pulls the live endpoint + password from the repo files (no
upload, no GitHub login, no tokens needed for public repos), saves
everything, starts the local tunnel and opens Chrome through the USA IP.

First-time server setup is manual (once): download ipnet-bundle.zip from
Releases, upload its folder to a new repo (GitHub web UI), and the
workflow starts by itself and keeps itself alive.

Windows: config at %APPDATA%/IPNET/config.json (chosen at setup).
Needs on PC: internet + Chrome.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

APP_NAME = "IPNET"
APP_VERSION = "v1.3.1"
TEMPLATE_URL = "https://github.com/X5Coder/proxy-usa"
APP_AUTHOR = "X5Coder"
RAW = "https://raw.githubusercontent.com"
SB_VERSION = "1.14.2"
SS_METHOD = "aes-256-gcm"
LOCAL_SOCKS_PORT = 1080


def slog(*args, **kwargs):
    """print() that never kills the app: with no live console (odd launch,
    broken pipe) stdout writes raise OSError - swallow it and keep running."""
    try:
        print(*args, **kwargs)
    except OSError:
        pass


def _default_data_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "IPNET")
    return os.path.join(os.path.expanduser("~"), ".ipnet")


def _pointer_file():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "IPNET.datadir")
    return os.path.join(os.path.expanduser("~"), ".ipnet-datadir")


def get_data_dir():
    """User-chosen storage dir (registry on Windows, pointer file elsewhere)."""
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\IPNET") as k:
                d, _ = winreg.QueryValueEx(k, "DataDir")
                if d and os.path.isdir(d):
                    return d
        except Exception:
            pass
    try:
        if os.path.exists(_pointer_file()):
            with open(_pointer_file(), "r", encoding="utf-8") as f:
                d = f.read().strip()
            if d and os.path.isdir(d):
                return d
    except Exception:
        pass
    # keep existing installs working (old dir or fresh default)
    if os.path.exists(os.path.join(_default_data_dir(), "config.json")):
        return _default_data_dir()
    if os.name == "nt":
        old = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "X5Proxy")
    else:
        old = os.path.join(os.path.expanduser("~"), ".x5proxy")
    if os.path.exists(os.path.join(old, "config.json")):
        return old
    return _default_data_dir()


def set_data_dir(d):
    d = os.path.abspath(d)
    os.makedirs(d, exist_ok=True)
    if os.name == "nt":
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\IPNET") as k:
                winreg.SetValueEx(k, "DataDir", 0, winreg.REG_SZ, d)
            return
        except Exception:
            pass
    try:
        with open(_pointer_file(), "w", encoding="utf-8") as f:
            f.write(d)
    except Exception:
        pass


def app_dir():
    d = get_data_dir()
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(app_dir(), "config.json")


def resource_path(name):
    """Find bundled asset (works in dev and in PyInstaller EXE)."""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(os.path.join(base, name)):
        return os.path.join(base, name)
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.exists(here):
        return here
    return ""


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("owner") and cfg.get("repo") and cfg.get("password"):
            return cfg
        return None
    except Exception:
        return None


def save_config(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def raw_get(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def tunnel_log_path():
    return os.path.join(app_dir(), "singbox.log")


def parse_repo_url(s):
    s = (s or "").strip().strip('"').strip("'")
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", s)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"([^/\s]+)/([^/\s]+?)(?:\.git)?$", s)
    if m and "/" in s and " " not in s:
        return m.group(1), m.group(2)
    return None


def extract_password_from_repo_text(singbox_text="", workflow_text="", server_text=""):
    """Extract Shadowsocks password from public repo files.
    Priority: singbox-server.json -> proxy.yml PROXY_PASS -> server.py."""
    method = SS_METHOD
    if singbox_text:
        try:
            data = json.loads(singbox_text)
            for inbound in data.get("inbounds", []):
                pwd = inbound.get("password")
                m = inbound.get("method")
                if pwd:
                    if m:
                        method = m
                    return pwd, method
        except Exception:
            pass
        m = re.search(r'"password"\s*:\s*"([^"]{4,128})"', singbox_text)
        if m:
            return m.group(1), method
    if workflow_text:
        m = re.search(r"PROXY_PASS='([^']{4,128})'", workflow_text)
        if m:
            return m.group(1), method
        m = re.search(r'PROXY_PASS="([^"]{4,128})"', workflow_text)
        if m:
            return m.group(1), method
    if server_text:
        m = re.search(r'PROXY_PASSWORD",\s*"([^"]{4,128})"', server_text)
        if m:
            return m.group(1), method
    return "", method


def fetch_public_repo_snapshot(owner, repo):
    """Read-only check of a PUBLIC repo (no login). Returns
    {endpoint, endpoint_file, password, method, has_code}."""
    base = f"{RAW}/{owner}/{repo}/main"
    ss_endpoint = raw_get(f"{base}/ss_url.txt")
    bore_endpoint = raw_get(f"{base}/bore_url.txt")
    endpoint, endpoint_file = "", ""
    if ss_endpoint and re.match(r"bore\.pub:\d+", ss_endpoint):
        endpoint, endpoint_file = ss_endpoint, "ss_url.txt"
    elif bore_endpoint and re.match(r"bore\.pub:\d+", bore_endpoint):
        endpoint, endpoint_file = bore_endpoint, "bore_url.txt"
    singbox_text = raw_get(f"{base}/singbox-server.json")
    workflow_text = raw_get(f"{base}/.github/workflows/proxy.yml")
    has_code = bool(singbox_text or workflow_text)
    server_text = ""
    if not has_code:
        server_text = raw_get(f"{base}/server.py")
        has_code = bool(server_text and "proxy" in server_text.lower())
    password, method = extract_password_from_repo_text(
        singbox_text, workflow_text, server_text)
    return {"endpoint": endpoint, "endpoint_file": endpoint_file,
            "password": password, "method": method, "has_code": has_code}


def setup_attach(repo_text, log):
    """Follow-only attach (public repos only, no login, no token).
    Pulls endpoint+password from the repo's public files and saves them.
    Raises RuntimeError with a plain message when there is nothing
    usable yet (wrong link / still building / code missing)."""
    parsed = parse_repo_url(repo_text or "")
    if not parsed:
        raise RuntimeError("Paste a repo link, e.g. https://github.com/YOU/my-proxy")
    owner, repo = parsed
    log(f"Checking {owner}/{repo} ...")
    snap = fetch_public_repo_snapshot(owner, repo)
    if not snap["has_code"]:
        raise RuntimeError("No proxy code in this repo yet. Create it from the "
                           "template first (Step 1), then paste its link here.")
    if not snap["password"]:
        raise RuntimeError("Code found but password unreadable - recreate from template.")
    cfg = {"owner": owner, "repo": repo, "password": snap["password"],
           "method": snap.get("method") or SS_METHOD,
           "attached": True, "readonly": True}
    save_config(cfg)
    if snap["endpoint"]:
        log(f"Attached! Live endpoint: {snap['endpoint']}")
        return cfg
    # First build still running: WAIT here (up to ~12 min) with live
    # progress, so the window only closes into run mode (and Chrome)
    # when there is something to connect to.
    log("Server is building for the first time - waiting for it ...")
    started = time.time()
    for _i in range(48):
        time.sleep(15)
        v = raw_get(f"{RAW}/{owner}/{repo}/main/ss_url.txt")
        if v and re.match(r"bore\.pub:\d+", v):
            log(f"Ready! Endpoint: {v}")
            return cfg
        mins = int((time.time() - started) // 60) + 1
        log(f"... still building (~{mins} min elapsed, "
            f"see https://github.com/{owner}/{repo}/actions)")
    log("Still building - the app will pick it up automatically.")
    return cfg


def gui_setup(error_msg=""):
    """IPNET setup window. Editorial minimalism: warm white, off-black type,
    hairline dividers, one solid CTA. Returns cfg or None if closed."""
    import tkinter as tk
    result = {}

    # DPI awareness: without this Windows bitmap-scales the window (blurry)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    PAPER, INK, MUTED, HAIR, FIELD, CTA, CTA_HOVER, ERR_BG, ERR_TX = (
        "#FBFBFA", "#111111", "#787774", "#EAEAEA", "#FFFFFF",
        "#111111", "#333333", "#FDEBEC", "#9F2F2D")

    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION} - Setup")
    root.geometry("560x640")
    root.minsize(500, 540)
    root.resizable(True, True)
    root.configure(bg=PAPER)

    def _set_window_icon(window):
        """Crisp icon: .ico for taskbar/titlebar (Windows picks the right
        size layer), plus a pre-rendered 32px PNG for iconphoto so Tk does
        not blur a 256px image down at runtime. SVG is never used directly
        (Tk/Windows cannot render SVG sharply)."""
        try:
            p_ico = resource_path("ipnet.ico")
            if p_ico and os.path.exists(p_ico):
                window.iconbitmap(p_ico)
        except Exception:
            pass
        for _name in ("ipnet-32.png", "ipnet.png"):
            _p = resource_path(_name)
            if _p and os.path.exists(_p):
                try:
                    _img = tk.PhotoImage(file=_p)
                    window.iconphoto(True, _img)
                    window._icon_ref = _img  # keep alive
                    break
                except Exception:
                    continue

    _set_window_icon(root)

    # thin top rule + compact header (no logo, version lives in footer)
    tk.Frame(root, bg=INK, height=3).pack(fill="x")
    wrap = tk.Frame(root, bg=PAPER)
    wrap.pack(fill="both", expand=True)
    from tkinter import ttk as _ttk
    _style = _ttk.Style()
    try:
        _style.theme_use("clam")
    except Exception:
        pass
    _style.configure("IPNET.Vertical.TScrollbar", background=PAPER,
                     troughcolor=PAPER, bordercolor=PAPER,
                     arrowcolor=MUTED, gripcount=0)
    _style.map("IPNET.Vertical.TScrollbar", background=[("active", HAIR)])
    canvas = tk.Canvas(wrap, bg=PAPER, highlightthickness=0, borderwidth=0)
    scroll = _ttk.Scrollbar(wrap, orient="vertical",
                            command=canvas.yview,
                            style="IPNET.Vertical.TScrollbar")
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    body = tk.Frame(canvas, bg=PAPER)
    win_id = canvas.create_window((0, 0), window=body, anchor="nw")

    def _fit_width(_evt=None):
        canvas.itemconfig(win_id, width=canvas.winfo_width())
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", _fit_width)

    def _sync_scroll(_evt=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    body.bind("<Configure>", _sync_scroll)

    def _wheel(evt):
        canvas.yview_scroll(-1 if evt.delta > 0 else 1, "units")

    canvas.bind_all("<MouseWheel>", _wheel)
    root.protocol("WM_DELETE_WINDOW", lambda: (canvas.unbind_all("<MouseWheel>"),
                                               root.destroy()))

    wrap = tk.Frame(body, bg=PAPER)  # content parent (scrolls)
    wrap.pack(fill="both", expand=True, padx=28, pady=18)

    # ---------- design helpers: toast + rounded buttons ----------
    def show_toast(message="Copied!"):
        """Small dark pill notification near the window, auto-hides."""
        try:
            tip = tk.Toplevel(root)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tip.configure(bg=PAPER)
            pill = tk.Label(tip, text=message, bg="#111111", fg="#FFFFFF",
                            font=("Segoe UI", 9), padx=14, pady=7)
            pill.pack()
            root.update_idletasks()
            x = root.winfo_x() + (root.winfo_width() - tip.winfo_reqwidth()) // 2
            y = root.winfo_y() + root.winfo_height() - 90
            tip.geometry(f"+{x}+{y}")
            tip.after(1400, tip.destroy)
        except Exception:
            pass

    def copy_text(text, message="Copied!"):
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
        except Exception:
            pass
        show_toast(message)

    class RoundedButton(tk.Canvas):
        """tk.Button can't do rounded corners, so this Canvas-drawn button
        paints a real rounded rectangle (crisp vector, states included)."""

        def __init__(self, parent, text, command=None, width=220, height=46,
                     radius=14, bg= PAPER, fg="#FFFFFF",
                     normal="#111111", hover="#2E2E2E", pressed="#000000",
                     disabled="#9CA3AF", font=("Segoe UI", 11, "bold"),
                     border=0, border_color="#EAEAEA"):
            super().__init__(parent, width=width, height=height, bg=bg,
                             highlightthickness=0, borderwidth=0, relief="flat")
            self._cmd = command
            self._colors = {"normal": normal, "hover": hover,
                            "pressed": pressed, "disabled": disabled}
            self._fg = fg
            self._radius = radius
            self._bw, self._bh = width, height
            self._border = border
            self._border_color = border_color
            self._state = "normal"
            self._text = text
            self._font = font
            self._bg_parent = bg
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)
            self.configure(cursor="hand2")
            self._draw("normal")

        def _round_points(self, x1, y1, x2, y2, r):
            pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r,
                   x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r,
                   x1, y1+r, x1, y1, x1+r, y1]
            return pts

        def _draw(self, state):
            self.delete("all")
            c = self._colors[state]
            r = self._radius
            w, h = self._bw, self._bh
            # parent-bg backdrop to avoid canvas corners showing
            self.create_rectangle(0, 0, w, h, fill=self._bg_parent, outline=self._bg_parent)
            if self._border:
                self.create_polygon(self._round_points(1, 1, w-1, h-1, r),
                                    fill=self._border_color, outline="", smooth=True)
                self.create_polygon(self._round_points(2, 2, w-2, h-2, r-1),
                                    fill=c, outline="", smooth=True)
            else:
                self.create_polygon(self._round_points(1, 1, w-1, h-1, r),
                                    fill=c, outline="", smooth=True)
            fill = self._fg if state != "disabled" else "#FFFFFF"
            self.create_text(w//2, h//2, text=self._text, fill=fill, font=self._font)

        def _on_enter(self, _e=None):
            if self._state == "normal":
                self._draw("hover")

        def _on_leave(self, _e=None):
            if self._state == "normal":
                self._draw("normal")

        def _on_press(self, _e=None):
            if self._state == "normal":
                self._draw("pressed")

        def _on_release(self, _e=None):
            if self._state != "normal":
                return
            self._draw("hover")
            if callable(self._cmd):
                self._cmd()

        def set_enabled(self, on):
            self._state = "normal" if on else "disabled"
            self._draw("normal" if on else "disabled")
            self.configure(cursor="hand2" if on else "arrow")

    tk.Label(wrap, text=APP_NAME, bg=PAPER, fg=INK,
             font=("Segoe UI", 15, "bold")).pack(anchor="w")
    tk.Label(wrap, text="USA proxy in one click.", bg=PAPER, fg=MUTED,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 12))

    def hairline():
        tk.Frame(wrap, bg=HAIR, height=1).pack(fill="x", pady=10)

    tk.Label(wrap, text="USA proxy in one click.", bg=PAPER, fg=MUTED,
             font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 14))

    saved_cfg = load_config() or {}
    saved_link = ""
    if saved_cfg.get("owner") and saved_cfg.get("repo"):
        saved_link = f"https://github.com/{saved_cfg['owner']}/{saved_cfg['repo']}"

    tk.Label(wrap, text="1  —  Make your own copy (once)", bg=PAPER, fg=INK,
             font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Open the original repo, press \"Use this template\", "
                        "create yours. Click the link to copy it.",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
    LINK_BG, LINK_FG = "#EFF6FF", "#1D4ED8"
    link_card = tk.Frame(wrap, bg=LINK_BG, highlightthickness=1,
                         highlightbackground="#BFDBFE")
    link_card.pack(fill="x", pady=3)
    link_lbl = tk.Label(link_card, text=TEMPLATE_URL,
                        bg=LINK_BG, fg=LINK_FG, cursor="hand2",
                        font=("Consolas", 9, "underline"))
    link_lbl.pack(side="left", padx=10, pady=8)
    hint_lbl = tk.Label(link_card, text="Click to copy",
                        bg=LINK_BG, fg="#60A5FA", font=("Segoe UI", 8))
    hint_lbl.pack(side="right", padx=10)

    def _copy_template(_evt=None):
        copy_text(TEMPLATE_URL, "Link copied!")

    for _w in (link_card, link_lbl, hint_lbl):
        _w.bind("<Button-1>", _copy_template)
        _w.configure(cursor="hand2")
    hairline()

    tk.Label(wrap, text="2  —  Your new repo link", bg=PAPER, fg=INK,
             font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Paste YOUR copy's link here, then Start. It is checked "
                        "first, then Chrome opens through the USA IP.",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
    repo_var = tk.StringVar(value=saved_link)
    tk.Entry(wrap, textvariable=repo_var, bg=FIELD, fg=INK, relief="solid",
             borderwidth=1, highlightthickness=1, highlightcolor=INK,
             highlightbackground=HAIR, font=("Segoe UI", 9),
             insertbackground=INK).pack(fill="x", pady=3)
    hairline()

    tk.Label(wrap, text="Paste the link, press Start. No login, no tokens.",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 12))

    status = tk.StringVar(value=error_msg)
    status_lbl = tk.Label(wrap, textvariable=status, bg=PAPER, fg=ERR_TX,
                          wraplength=520, justify="left", font=("Segoe UI", 9))
    status_lbl.pack(anchor="w", pady=(0, 8))

    from tkinter import ttk
    pb = ttk.Progressbar(wrap, mode="indeterminate", length=440)
    # hidden until Start is pressed

    # rounded CTA (Canvas-drawn, states: normal/hover/pressed/disabled)
    enabled = {"v": True}
    btn_holder = tk.Frame(wrap, bg=PAPER)
    btn_holder.pack(pady=12)
    btn = RoundedButton(btn_holder, text="Start →", command=lambda: on_start(),
                        width=240, height=50, radius=16,
                        bg=PAPER, fg="#FFFFFF",
                        normal=CTA, hover=CTA_HOVER, pressed="#000000",
                        disabled="#9CA3AF",
                        font=("Segoe UI", 12, "bold"))
    btn.pack()

    def on_start():
        if not enabled["v"]:
            return
        link = (repo_var.get() or "").strip()
        if not link:
            status.set("Paste your repo link first.")
            return
        enabled["v"] = False
        btn.set_enabled(False)
        try:
            set_data_dir(get_data_dir())
        except Exception as e:
            status.set(f"Cannot use storage folder: {e}")
            enabled["v"] = True
            btn.set_enabled(True)
            return
        status.set("Checking the repo ...")
        pb.pack(fill="x", pady=(0, 4))
        pb.start(12)

        def log(msg):
            status.set(msg)
            try:
                root.update_idletasks()
                root.update()
            except Exception:
                pass

        root.update()
        try:
            cfg = setup_attach(link, log)
            result["cfg"] = cfg
            status.set("Ready! Starting ...")
            pb.stop()
            root.update()
            time.sleep(1)
            root.destroy()
        except KeyboardInterrupt:
            pb.stop()
            pb.pack_forget()
            status.set("Cancelled - press Start to retry.")
            enabled["v"] = True
            btn.set_enabled(True)
        except Exception as e:
            pb.stop()
            pb.pack_forget()
            status.set(f"Error: {e}")
            enabled["v"] = True
            btn.set_enabled(True)

    tk.Frame(wrap, bg=HAIR, height=1).pack(fill="x", pady=(10, 8))
    tk.Label(wrap, text=f"{APP_NAME} {APP_VERSION} — by {APP_AUTHOR}", bg=PAPER, fg=MUTED,
             font=("Consolas", 8)).pack(anchor="center")
    tk.Label(wrap, text="Original: github.com/X5Coder/proxy-usa", bg=PAPER, fg=MUTED,
             font=("Consolas", 8)).pack(anchor="center")
    root.mainloop()
    return result.get("cfg")


def ensure_singbox():
    d = os.path.join(app_dir(), "bin")
    os.makedirs(d, exist_ok=True)
    if os.name == "nt":
        exe = os.path.join(d, "sing-box.exe")
        asset = f"sing-box-{SB_VERSION}-windows-amd64.zip"
    else:
        exe = os.path.join(d, "sing-box")
        asset = f"sing-box-{SB_VERSION}-linux-amd64.tar.gz"
    if os.path.exists(exe):
        return exe
    slog(f"Downloading sing-box {SB_VERSION} (one time)...", flush=True)
    url = f"https://github.com/SagerNet/sing-box/releases/download/v{SB_VERSION}/{asset}"
    tmp = os.path.join(d, asset)
    urllib.request.urlretrieve(url, tmp)
    if tmp.endswith(".zip"):
        with zipfile.ZipFile(tmp, "r") as z:
            z.extractall(d)
        for root, _, files in os.walk(d):
            if "sing-box.exe" in files:
                shutil.copy(os.path.join(root, "sing-box.exe"), exe)
                break
    else:
        import tarfile
        with tarfile.open(tmp, "r:gz") as t:
            t.extractall(d)
        for root, _, files in os.walk(d):
            if "sing-box" in files:
                shutil.copy(os.path.join(root, "sing-box"), exe)
                break
    try:
        os.remove(tmp)
    except Exception:
        pass
    if os.name != "nt":
        os.chmod(exe, 0o755)
    return exe


def find_chrome():
    if os.name == "nt":
        for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")):
            if c and os.path.exists(c):
                return c
        return shutil.which("chrome")
    for c in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(c)
        if p:
            return p
    return None


def fetch_endpoint(cfg):
    # Public raw files: ss_url.txt preferred, bore_url.txt fallback.
    for name in ("ss_url.txt", "bore_url.txt"):
        v = raw_get(f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/{name}")
        if v and re.match(r"bore\.pub:\d+", v):
            return name, v
    return "", ""


def free_local_port():
    """Kill a stale tunnel from a previous run so port 1080 is free."""
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCAL_SOCKS_PORT))
        s.close()
        return  # free
    except OSError:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/IM", "sing-box.exe"],
                           capture_output=True, timeout=10)
        else:
            subprocess.run(["pkill", "-f", "sb-client.json"],
                           capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(2)


def proxy_working(timeout=12):
    """True only if traffic REALLY flows end-to-end: SOCKS5 handshake on
    127.0.0.1:1080 + a CONNECT request through the Shadowsocks server.
    A plain TCP check against bore.pub is NOT enough: the tunnel can be
    up while the server-side proxy is dead and refusing every connection
    (the singbox.log ERROR flood). Pure stdlib, no extra dependency."""
    import socket
    s = None
    try:
        s = socket.create_connection(("127.0.0.1", LOCAL_SOCKS_PORT),
                                     timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")  # SOCKS5, no auth
        if s.recv(2) != b"\x05\x00":
            return False
        host = b"www.gstatic.com"
        req = (b"\x05\x01\x00\x03" + bytes([len(host)]) + host +
               b"\x01\xbb")  # CONNECT host:443
        s.sendall(req)
        resp = s.recv(10)
        return len(resp) >= 2 and resp[1] == 0x00
    except Exception:
        return False
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def start_tunnel(exe, client_cfg):
    """Start sing-box quietly (logs go to a file, terminal stays clean)."""
    lf = open(tunnel_log_path(), "a", encoding="utf-8")
    proc = subprocess.Popen([exe, "run", "-c", client_cfg],
                            stdout=lf, stderr=subprocess.STDOUT,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    return proc, lf


def stop_tunnel(proc, lf):
    try:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    except Exception:
        pass
    try:
        if lf:
            lf.close()
    except Exception:
        pass


def seed_chrome_profile(profile):
    """Write privacy prefs into the USA profile BEFORE Chrome starts.

    Fully automatic (the app does it on every launch, no user steps):
    - Accept-Language en-US (existing behavior).
    - webrtc.ip_handling_policy = disable_non_proxied_udp at PROFILE
      level. This is what actually stops the leak: the CLI switch alone
      is ignored once WebRTC has ever run in the profile, but the stored
      profile pref wins every time and survives restarts.
    Existing keys are preserved; Chrome must not be running on this
    profile while we write (our flow always writes before first launch).
    """
    prefs = os.path.join(profile, "Preferences")
    try:
        data = {}
        if os.path.exists(prefs):
            try:
                with open(prefs, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        intl = data.get("intl")
        if not isinstance(intl, dict):
            intl = {}
        intl["accept_languages"] = "en-US,en"
        data["intl"] = intl
        web = data.get("webrtc")
        if not isinstance(web, dict):
            web = {}
        web["ip_handling_policy"] = "disable_non_proxied_udp"
        data["webrtc"] = web
        # DNS-over-HTTPS through the proxy (UDP DNS relay is impossible
        # over bore's TCP-only tunnel, so plain UDP DNS would leak to the
        # ISP - DoH keeps name resolution inside the encrypted stream).
        doh = data.get("dns_over_https")
        if not isinstance(doh, dict):
            doh = {}
        doh["mode"] = "secure"
        doh["templates"] = "https://1.1.1.1/dns-query{?dns}"
        data["dns_over_https"] = doh
        with open(prefs, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        slog(f"Profile seed failed: {e}", flush=True)
        return False


def open_usa_chrome(chrome, url=None):
    """Open Chrome with a USA identity: English UI+content, no WebRTC leak.
    url is opened only when given (first run); otherwise a normal window."""
    profile = os.path.join(app_dir(), "chrome-usa")
    os.makedirs(profile, exist_ok=True)
    seed_chrome_profile(profile)
    # Stale USA window check: Chrome owns Preferences while running, so a
    # leftover window from an older version would keep the OLD (leaky)
    # settings. Warn loudly instead of silently leaking.
    try:
        locked = os.path.exists(os.path.join(profile, "lockfile")) or os.path.exists(
            os.path.join(profile, "SingletonSocket"))
    except Exception:
        locked = False
    # Read-back: prove what the profile will enforce (visible in terminal).
    try:
        with open(os.path.join(profile, "Preferences"), "r", encoding="utf-8") as f:
            cur = json.load(f) or {}
        slog(f"WebRTC policy armed: {cur.get('webrtc', {}).get('ip_handling_policy')} | "
             f"DoH: {cur.get('dns_over_https', {}).get('mode')}" +
             (" | WARNING: old USA Chrome window still open - close it!" if locked else ""),
             flush=True)
    except Exception:
        pass
    try:
        args = [
            chrome, f"--user-data-dir={profile}",
            f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
            "--lang=en-US",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]
        if url:
            args.append(url)
        subprocess.Popen(args)
        slog("Chrome opened (USA profile: English, WebRTC leak blocked).",
              flush=True)
    except Exception as e:
        slog(f"Could not open Chrome: {e}", flush=True)


def run_terminal(cfg):
    """Terminal loop: show proxy address, refresh endpoint, open Chrome.
    Raises RuntimeError if the repo/endpoint is unusable -> GUI reopens."""
    free_local_port()
    exe = ensure_singbox()
    chrome = find_chrome()
    if not chrome:
        slog("WARNING: Chrome not found. Install Google Chrome first.")
    # keep the tunnel log from growing forever (old ERROR floods)
    try:
        _lp = tunnel_log_path()
        if os.path.exists(_lp) and os.path.getsize(_lp) > 2 * 1024 * 1024:
            open(_lp, "w").close()
            slog("Old tunnel log cleared (>2MB).", flush=True)
    except Exception:
        pass
    proc = None
    tun_log = None
    current = ""
    dead = 0
    client_cfg = os.path.join(app_dir(), "sb-client.json")
    slog("=" * 60)
    slog(f"  {APP_NAME} {APP_VERSION} - USA proxy (leave this window OPEN)")
    slog("=" * 60)
    slog(f"Repo: {cfg['owner']}/{cfg['repo']}")
    slog("Press Ctrl+C to stop.\n", flush=True)
    fails = 0
    first_run = True
    chrome_opened = False  # open Chrome once per process: renewals must
    # NOT spawn another window while one is already open
    try:
        while True:
            name, endpoint = fetch_endpoint(cfg)
            if not endpoint:
                fails += 1
                slog(f"Endpoint not published yet ({fails}) - next check in ~1 min. "
                      f"Follow https://github.com/{cfg['owner']}/{cfg['repo']}/actions",
                      flush=True)
                if fails >= 10:
                    raise RuntimeError("No endpoint published. Re-enter the repo URL.")
                time.sleep(60)
                continue
            fails = 0
            if endpoint != current:
                current = endpoint
                host, _, port = endpoint.partition(":")
                ccfg = {
                    "log": {"level": "error"},
                    "inbounds": [{"type": "mixed", "tag": "in",
                                  "listen": "127.0.0.1",
                                  "listen_port": LOCAL_SOCKS_PORT}],
                    "outbounds": [{"type": "shadowsocks", "tag": "out",
                                   "server": host.strip(),
                                   "server_port": int(port),
                                   "method": cfg.get("method", SS_METHOD),
                                   "password": cfg["password"]}],
                }
                with open(client_cfg, "w", encoding="utf-8") as f:
                    json.dump(ccfg, f)
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                # startup check: dead on arrival -> the server self-heals and
                # publishes a new endpoint; we just follow it (follow-only).
                if first_run and not proxy_working():
                    first_run = False
                    slog("Proxy not responding on startup - "
                          "waiting for the server's fresh endpoint ...", flush=True)
                first_run = False
                slog("-" * 60)
                slog(f"PROXY ADDRESS (manual use): 127.0.0.1:{LOCAL_SOCKS_PORT} (SOCKS5 + HTTP)")
                slog(f"SERVER: {endpoint} "
                      f"({'encrypted' if name == 'ss_url.txt' else 'plain http'})")
                slog("IP: USA (Phoenix, Arizona)")
                slog("-" * 60, flush=True)
                if chrome and not chrome_opened:
                    chrome_opened = True
                    if not cfg.get("welcomed"):
                        open_usa_chrome(chrome, "https://ipleak.net/")
                        cfg["welcomed"] = True
                        save_config(cfg)
                    else:
                        open_usa_chrome(chrome)
                elif chrome:
                    slog("Endpoint renewed - using the already-open Chrome "
                          "window (no new window).", flush=True)
            if proc and proc.poll() not in (None, 0):
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                slog("Local tunnel restarted.", flush=True)
            # --- client-side healing: does traffic REALLY flow? ---
            # (TCP to bore.pub is not enough: the tunnel can be up while
            # the server-side proxy refuses everything -> ERROR flood.)
            if current and proxy_working():
                if dead:
                    slog("Proxy is working again.", flush=True)
                dead = 0
            elif current:
                dead += 1
                if dead == 1 or dead % 3 == 0:
                    slog(f"Proxy not responding ({dead}) - server self-heals, "
                          "following its fresh endpoint ...", flush=True)
                # Follow-only: the workflow heals itself on FIRST failure and
                # publishes a new endpoint; the loop above picks it up.
            time.sleep(20)
    except KeyboardInterrupt:
        slog("\nStopping...")
    finally:
        stop_tunnel(proc, tun_log)


def main():
    if "--reset" in sys.argv:
        try:
            os.remove(config_path())
        except Exception:
            pass
    try:
        # Same screen on EVERY launch, prefilled with the last saved link.
        while True:
            cfg = gui_setup()
            if not cfg:
                return  # user closed the window
            try:
                run_terminal(cfg)
                return
            except RuntimeError as e:
                slog(f"Problem: {e}", flush=True)
                continue  # reopen the same screen with saved values
    except KeyboardInterrupt:
        slog("\nStopping...")
    except Exception as e:
        try:
            import traceback
            traceback.print_exc()
        except Exception:
            pass
        slog(f"\nUnexpected error: {e}", flush=True)
        try:
            input("Press Enter to close ...")
        except Exception:
            pass


if __name__ == "__main__":
    main()
