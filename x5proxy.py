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
APP_VERSION = "v1.5.9"
TEMPLATE_URL = "https://github.com/X5Coder/IPNET"
APP_AUTHOR = "X5Coder"
RAW = "https://raw.githubusercontent.com"
SB_VERSION = "1.14.2"
SS_METHOD = "aes-256-gcm"
LOCAL_SOCKS_PORT = 1080
# Endpoint hysteresis: an endpoint that just failed is not trusted again
# until this cooldown passes (kills flip-flop storms when two server
# generations overwrite the same file back and forth).
BAD_EP_COOLDOWN = 180
_bad_until = {}


def mark_bad(ep):
    _bad_until[ep] = time.time() + BAD_EP_COOLDOWN


def is_bad(ep):
    try:
        if _bad_until.get(ep, 0) > time.time():
            return True
        _bad_until.pop(ep, None)
        return False
    except Exception:
        return False


def is_admin():
    """True if this process is elevated (Windows) / root (posix)."""
    try:
        if os.name == "nt":
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def elevated_cmd():
    """Argv that re-runs THIS app elevated (Windows runas). Pure builder."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--elevated"]
    return [sys.executable, os.path.abspath(__file__), "--elevated"]


def try_elevate(reason):
    """Relaunch self with admin rights (one UAC prompt). Returns True if
    the elevated copy was launched (caller must exit). Pure stdlib."""
    if os.name != "nt":
        return False
    try:
        cmd = elevated_cmd()
        ps = ("Start-Process -FilePath '" + cmd[0].replace("'", "''") + "'"
              + (" -ArgumentList '" + " ".join(
                  a.replace("'", "''") for a in cmd[1:]) + "'"
                 if len(cmd) > 1 else "")
              + " -Verb RunAs -PassThru")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            slog(f"[admin] elevated copy launched ({reason}) - "
                 "this window will close.", flush=True)
            return True
        slog("[admin] elevation declined/failed - continuing unelevated.",
             flush=True)
    except Exception as e:
        slog(f"[admin] elevation failed: {e} - continuing unelevated.",
             flush=True)
    return False
# Yggdrasil (second transport, preferred when usable; bore stays fallback).
YGG_VERSION = "0.5.14"
YGG_MSI_URL = ("https://github.com/yggdrasil-network/yggdrasil-go/releases/"
               "download/v0.5.14/yggdrasil-0.5.14-x64.msi")
YGG_PEERS = ("tls://mn.us.ygg.triplebit.org:993",
             "tls://marisa.nadeko.net:44442",
             "tls://ygg.mnpnk.com:443")
YGG_ADMIN = "tcp://127.0.0.1:9001"
YGG_SS_PORT = 8388


ELEVATED = "--elevated" in sys.argv


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


def raw_get(url, timeout=20, bust=False):
    """Read a public raw file. bust=True appends ?cb=<unix> and sends
    no-cache headers to dodge the Fastly edge cache (raw serves
    Cache-Control: max-age=300, so a plain branch URL can lag ~5 min
    behind a fresh push). Raw polling is free and unlimited, unlike the
    GitHub API (60 req/hr unauthenticated)."""
    try:
        if bust:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}cb={int(time.time())}"
        req = urllib.request.Request(url, headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
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
    ss_endpoint = raw_get(f"{base}/ss_url.txt", bust=True)
    bore_endpoint = raw_get(f"{base}/bore_url.txt", bust=True)
    endpoint, endpoint_file = "", ""
    if ss_endpoint and re.match(r"bore\.pub:\d+", ss_endpoint):
        endpoint, endpoint_file = ss_endpoint, "ss_url.txt"
    elif bore_endpoint and re.match(r"bore\.pub:\d+", bore_endpoint):
        endpoint, endpoint_file = bore_endpoint, "bore_url.txt"
    singbox_text = raw_get(f"{base}/singbox-server.json", bust=True)
    workflow_text = raw_get(f"{base}/.github/workflows/proxy.yml", bust=True)
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
        v = raw_get(f"{RAW}/{owner}/{repo}/main/ss_url.txt", bust=True)
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
    tk.Label(wrap, text="Original: github.com/X5Coder/IPNET", bg=PAPER, fg=MUTED,
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


# --- instant-update helpers (SHA-pinned fetch) ---
# raw branch URLs lag ~5 min (Fastly max-age=300, verified: X-Cache HIT,
# Source-Age ~294s). The commits API is fresh instantly, and a raw URL
# pinned to a commit SHA is immutable, so the CDN must MISS and serve the
# new file at once. The API is polled at most every ~90s PER PATH
# (unauthenticated limit is 60/hr -> two paths use ~80/hr worst case;
# normally far less since pins run only while down).
_last_sha_check = {}
_last_seen_sha = {}


def _api_latest_sha(owner, repo, path="ss_url.txt"):
    """Latest commit SHA touching <path>, or '' (throttled to ~90s/path)."""
    global _last_sha_check
    if time.time() - _last_sha_check.get(path, 0) < 90:
        return ""
    _last_sha_check[path] = time.time()
    url = (f"https://api.github.com/repos/{owner}/{repo}/commits"
           f"?path={path}&per_page=1&sha=main")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "ignore") or "[]")
        if data and isinstance(data, list) and data[0].get("sha"):
            return data[0]["sha"]
    except Exception:
        pass
    return ""


def _valid_ep(kind, v):
    v = (v or "").strip()
    if kind == "bore":
        return v if v and re.match(r"bore\.pub:\d+$", v) else ""
    m = re.match(r"^\[([0-9a-fA-F:]+)\]:(\d{1,5})$", v)
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def fetch_pinned(cfg, path, kind):
    """Fresh endpoint via SHA-pinned raw URL (bypasses branch cache).
    kind: 'bore' (ss_url.txt/bore_url.txt) or 'ygg' (ss_ygg_url.txt).
    Returns (name, endpoint) or ('','')."""
    global _last_seen_sha
    sha = _api_latest_sha(cfg["owner"], cfg["repo"], path)
    if not sha or sha == _last_seen_sha.get(path, ""):
        return "", ""
    names = ("ss_url.txt", "bore_url.txt") if kind == "bore" \
        else ("ss_ygg_url.txt",)
    for name in names:
        v = _valid_ep(kind, raw_get(
            f"{RAW}/{cfg['owner']}/{cfg['repo']}/{sha}/{name}", timeout=15))
        if v:
            _last_seen_sha[path] = sha
            return name, v
    _last_seen_sha[path] = sha  # seen but no endpoint; don't refetch
    return "", ""


def fetch_pinned_endpoint(cfg):
    """Back-compat: pinned bore endpoint."""
    return fetch_pinned(cfg, "ss_url.txt", "bore")


def fetch_pinned_ygg(cfg):
    """Pinned ygg endpoint."""
    return fetch_pinned(cfg, "ss_ygg_url.txt", "ygg")


def fetch_endpoint(cfg):
    # Public raw files with cache-buster: ss_url.txt preferred,
    # bore_url.txt fallback. (Full freshness via fetch_pinned_endpoint.)
    for name in ("ss_url.txt", "bore_url.txt"):
        v = raw_get(f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/{name}",
                    bust=True)
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
    """Back-compat wrapper around check_tunnel (default local port)."""
    ok, _ = check_tunnel(LOCAL_SOCKS_PORT, timeout)
    return ok


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


# ---------------- Yggdrasil second transport (preferred, bore fallback) ---
_ygg_proc = None


def ygg_dir():
    d = os.path.join(app_dir(), "ygg")
    os.makedirs(d, exist_ok=True)
    return d


def ensure_yggdrasil():
    """Download + extract the Windows yggdrasil binary once (like sing-box).
    Returns yggdrasil.exe path or '' (then bore simply continues)."""
    if os.name != "nt":
        slog("[ygg] auto-setup is Windows-only here - bore continues. "
             "(Linux: apt install yggdrasil, then restart.)", flush=True)
        return ""
    d = os.path.join(ygg_dir(), "v" + YGG_VERSION)
    exe = os.path.join(d, "PFiles", "Yggdrasil", "yggdrasil.exe")
    ctl = os.path.join(d, "PFiles", "Yggdrasil", "yggdrasilctl.exe")
    if os.path.exists(exe) and os.path.exists(ctl):
        slog(f"[ygg] binary v{YGG_VERSION} ready.", flush=True)
        return exe
    slog(f"[ygg] downloading yggdrasil v{YGG_VERSION} (one time, ~6MB) ...",
         flush=True)
    os.makedirs(d, exist_ok=True)
    msi = os.path.join(ygg_dir(), f"yggdrasil-{YGG_VERSION}.msi")
    try:
        if not os.path.exists(msi):
            urllib.request.urlretrieve(YGG_MSI_URL, msi)
        slog("[ygg] extracting (no install, no admin) ...", flush=True)
        subprocess.run(["msiexec", "/a", msi, "/qn", f"TARGETDIR={d}"],
                       capture_output=True, timeout=120)
        time.sleep(3)
        if os.path.exists(exe) and os.path.exists(ctl):
            slog("[ygg] binary ready.", flush=True)
            return exe
    except Exception as e:
        slog(f"[ygg] setup failed: {e} - bore continues.", flush=True)
    slog("[ygg] setup failed - bore continues.", flush=True)
    return ""


def ygg_exit_hint():
    """Read ygg/ygg.log tail and translate a dead node into an actionable
    hint. Returns hint string (may be '')."""
    try:
        with open(os.path.join(ygg_dir(), "ygg.log"), "r", encoding="utf-8",
                  errors="ignore") as f:
            tail = f.read()[-3000:].lower()
        if "access is denied" in tail:
            return ("TUN blocked: Windows needs admin for the mesh interface. "
                    "Right-click IPNET.exe -> 'Run as administrator' and retry. "
                    "(One UAC click; bore keeps working meanwhile.)")
        if "panic" in tail or "fatal" in tail:
            last = [l for l in tail.splitlines()
                    if "panic" in l or "fatal" in l][-1].strip()[:160]
            return f"node error: {last}"
    except Exception:
        pass
    return ""


def clear_port_owner(port=9001):
    """Free 127.0.0.1:<port> from OUR OWN squatters before binding.

    Two IPNET copies (e.g. old version still running elevated) fight
    over the same admin port and the same ygg.conf: each launch kills
    the other's node and its own node then dies on bind ('exited at
    once' forever). So: whoever LISTENs on <port> and is one of ours
    (yggdrasil.exe or any IPNET* binary, except THIS process) is
    killed automatically. Anything foreign is only REPORTED, never
    touched. Returns list of killed 'name(pid)'.
    Windows-only (the ygg auto-setup itself is Windows-only here)."""
    killed = []
    if os.name != "nt":
        return killed
    try:
        me = os.getpid()
        ps = ("$c = Get-NetTCPConnection -LocalPort " + str(port) +
              " -State Listen -ErrorAction SilentlyContinue; "
              "foreach ($x in $c) { "
              "try { $p = Get-Process -Id $x.OwningProcess -ErrorAction Stop; "
              "\"{0}|{1}\" -f $x.OwningProcess, $p.ProcessName } "
              "catch { } }")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20)
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            pid_s, name = line.split("|", 1)
            if not pid_s.strip().isdigit():
                continue
            pid = int(pid_s.strip())
            if pid == me:
                continue
            nl = name.strip().lower()
            if nl == "yggdrasil" or nl.startswith("ipnet"):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=10)
                    killed.append(f"{name.strip()}({pid})")
                except Exception:
                    pass
            else:
                slog(f"[ygg] port {port} held by foreign "
                     f"'{name.strip()}({pid})' - NOT touched (close it "
                     f"manually if the node keeps dying).", flush=True)
    except Exception as e:
        slog(f"[ygg] port-{port} scan skipped: {e}", flush=True)
    for k in killed:
        slog(f"[ygg] auto-killed duplicate on port {port}: {k} "
             f"(same app, would deadlock the node).", flush=True)
    return killed


def start_ygg_node(exe):
    """Start our mesh node (stable identity kept in ygg.conf). Returns proc
    or None. No TUN needed for the daemon itself; packet flow needs the
    wintun driver (one-time admin) - the end-to-end check decides."""
    global _ygg_proc
    conf = os.path.join(ygg_dir(), "ygg.conf")
    try:
        # Order matters: FIRST free the admin port from our own squatters
        # (duplicate IPNET copy holding :9001 would kill our node on
        # bind), THEN clear stale node processes on our conf file.
        clear_port_owner(9001)
        # Stale node from a crashed run would hold :9001 and our conf -
        # clear only processes running OUR conf file, never anything else.
        try:
            if os.name == "nt":
                ps = ("Get-CimInstance Win32_Process -Filter \"Name='yggdrasil.exe'\" | "
                      "Where-Object { $_.CommandLine -like '*ygg.conf*' } | "
                      "ForEach-Object { $_.ProcessId }")
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                    capture_output=True, text=True, timeout=20)
                for pid in (out.stdout or "").split():
                    if pid.strip().isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", pid.strip()],
                                       capture_output=True, timeout=10)
                        slog("[ygg] cleared stale node process.", flush=True)
            else:
                subprocess.run(["pkill", "-f", "ygg.conf"], capture_output=True,
                               timeout=10)
        except Exception:
            pass
        time.sleep(2)  # let the freed port settle before binding
        if not os.path.exists(conf):
            out = subprocess.run([exe, "-genconf"], capture_output=True,
                                 text=True, timeout=30)
            s = out.stdout or ""
            peers = "\n".join("    " + p for p in YGG_PEERS)
            s = s.replace("Peers: []", "Peers: [\n" + peers + "\n  ]")
            # Explicit TCP admin: genconf defaults vary by build (unix
            # socket / localhost). The client always dials
            # tcp://127.0.0.1:9001, so pin it here like the server does.
            # Ygg mesh is 200::/7 (2xxx AND 3xxx) - nothing else to touch.
            try:
                if "AdminListen:" in s:
                    s = re.sub(r"AdminListen:\s*\S+.*",
                               "AdminListen: tcp://127.0.0.1:9001", s)
                else:
                    s = s.rstrip()
                    assert s.endswith("}"), "yggdrasil genconf shape changed!"
                    s = s[:-1] + "\nAdminListen: tcp://127.0.0.1:9001\n}\n"
            except Exception:
                pass
            with open(conf, "w", encoding="utf-8") as f:
                f.write(s)
            slog("[ygg] fresh node identity generated (kept in ygg.conf).",
                 flush=True)
        else:
            # Old confs (pre-AdminListen pin) would leave yggdrasilctl
            # unable to reach the node -> node looks dead forever.
            # Patch the file once, in place, without touching the key.
            try:
                with open(conf, "r", encoding="utf-8") as f:
                    _s = f.read()
                if "127.0.0.1:9001" not in _s:
                    if "AdminListen:" in _s:
                        _s = re.sub(r"AdminListen:\s*\S+.*",
                                    "AdminListen: tcp://127.0.0.1:9001", _s)
                    else:
                        _s = _s.rstrip()
                        if _s.endswith("}"):
                            _s = _s[:-1] + "\nAdminListen: tcp://127.0.0.1:9001\n}\n"
                    with open(conf, "w", encoding="utf-8") as f:
                        f.write(_s)
                    slog("[ygg] conf patched: AdminListen pinned to 127.0.0.1:9001.",
                         flush=True)
                # Peers drift (dead public peers): ensure at least one of
                # the current YGG_PEERS is present.
                if not any(p in _s for p in YGG_PEERS):
                    _peers = "\n".join("    " + p for p in YGG_PEERS)
                    _s2 = open(conf, encoding="utf-8").read()
                    _s2 = re.sub(r"Peers:\s*\[[^\]]*\]",
                                 "Peers: [\n" + _peers + "\n  ]", _s2)
                    open(conf, "w", encoding="utf-8").write(_s2)
                    slog("[ygg] conf patched: peers refreshed.", flush=True)
            except Exception:
                pass
            slog("[ygg] reusing saved node identity.", flush=True)
        lf = open(os.path.join(ygg_dir(), "ygg.log"), "a", encoding="utf-8")
        _ygg_proc = subprocess.Popen(
            [exe, "-useconffile", conf], stdout=lf, stderr=subprocess.STDOUT,
            creationflags=0x08000000 if os.name == "nt" else 0)
        time.sleep(6)
        if _ygg_proc.poll() is not None:
            hint = ygg_exit_hint()
            slog("[ygg] node exited at once - see ygg/ygg.log. "
                 + (hint + " " if hint else "") + "bore continues.",
                 flush=True)
            _ygg_proc = None
            return None
        ip = ygg_node_ip(exe)
        slog(f"[ygg] node up. our mesh ip: {ip or 'unknown yet'}", flush=True)
        return _ygg_proc
    except Exception as e:
        slog(f"[ygg] node start failed: {e} - bore continues.", flush=True)
        return None


def ygg_node_ip(exe):
    """Our local mesh IPv6 (200::/7 -> 2xxx:... or 3xxx:...) or ''."""
    try:
        ctl = os.path.join(os.path.dirname(exe), "yggdrasilctl.exe")
        out = subprocess.run([ctl, "getSelf"], capture_output=True,
                             text=True, timeout=15)
        for line in (out.stdout or "").splitlines():
            if "/" in line:  # skip the /64 subnet line, want the address
                continue
            m = re.search(r"\b([23][0-9a-f]{2}:[0-9a-f:]+:[0-9a-f]+)\b",
                          line.lower())
            if m:
                return m.group(1)
        return ""
    except Exception:
        return ""


def ygg_peers_up(exe):
    """Best-effort count of 'Up' peerings, or -1."""
    try:
        ctl = os.path.join(os.path.dirname(exe), "yggdrasilctl.exe")
        out = subprocess.run([ctl, "getPeers"], capture_output=True,
                             text=True, timeout=15)
        return (out.stdout or "").count(" Up ")
    except Exception:
        return -1


def stop_ygg_node():
    global _ygg_proc
    try:
        if _ygg_proc and _ygg_proc.poll() is None:
            _ygg_proc.terminate()
            try:
                _ygg_proc.wait(timeout=5)
            except Exception:
                _ygg_proc.kill()
    except Exception:
        pass
    _ygg_proc = None


def fetch_ygg_endpoint(cfg):
    """Fresh Shadowsocks-over-mesh endpoint from ss_ygg_url.txt.
    File holds [ipv6]:port; returns ('ss_ygg_url.txt', 'ipv6:port') or ('','')."""
    v = raw_get(f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/ss_ygg_url.txt",
                bust=True)
    v = (v or "").strip()
    m = re.match(r"^\[([0-9a-fA-F:]+)\]:(\d{1,5})$", v)
    if m:
        return "ss_ygg_url.txt", f"{m.group(1)}:{m.group(2)}"
    return "", ""


def split_endpoint(ep):
    """'bore.pub:123' or '200:...:8388' -> (host, port).

    Accepts '[ipv6]:port' and bare 'ipv6:port' (last colon = port)."""
    s = (ep or "").strip()
    m = re.match(r"^\[([0-9a-fA-F:]+)\]:(\d{1,5})$", s)
    if m:
        try:
            return m.group(1), int(m.group(2))
        except Exception:
            return "", 0
    host, _, port = s.strip("[]").rpartition(":")
    try:
        return host.strip().strip("[]"), int(port)
    except Exception:
        return "", 0


def ygg_mesh_reachable(host, port, timeout=12):
    """Raw TCP to [mesh-ip]:port through the local ygg TUN.

    Cheap pre-gate before touching the live tunnel: proves L3 mesh
    routing exists (the old code jumped straight into rebuilding
    sing-box on an unroutable ghost IP). Returns (ok, reason)."""
    import socket
    s = None
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        return True, "mesh TCP open"
    except Exception as e:
        return False, f"mesh TCP: {type(e).__name__}"
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def probe_ygg_leg(exe, host, port, method, password, timeout=12):
    """End-to-end Shadowsocks-over-mesh test on a THROWAWAY local port.

    The live tunnel on 1080 (bore) is never touched: a temp sing-box
    on 127.0.0.1:1089 dials the mesh endpoint, check_tunnel(1089)
    proves real traffic, then the probe is killed. Returns (ok, reason).
    """
    import socket as _s
    probe_port = 1089
    try:
        _p = _s.socket()
        _p.bind(("127.0.0.1", probe_port))
        _p.close()
    except OSError:
        probe_port = 18089  # 1089 busy (stale probe) - use spare
    cfg = {"log": {"level": "error"},
           "inbounds": [{"type": "mixed", "tag": "probe",
                         "listen": "127.0.0.1",
                         "listen_port": probe_port}],
           "outbounds": [{"type": "shadowsocks", "tag": "out",
                          "server": host, "server_port": port,
                          "method": method, "password": password}]}
    tmp = os.path.join(app_dir(), "sb-ygg-probe.json")
    proc = None
    lf = None
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        lf = open(os.path.join(app_dir(), "ygg-probe.log"), "a",
                  encoding="utf-8")
        proc = subprocess.Popen(
            [exe, "run", "-c", tmp], stdout=lf, stderr=subprocess.STDOUT,
            creationflags=0x08000000 if os.name == "nt" else 0)
        time.sleep(3)
        if proc.poll() is not None:
            return False, "probe sing-box died at once"
        return check_tunnel(probe_port, timeout)
    except Exception as e:
        return False, f"probe: {type(e).__name__}"
    finally:
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


def build_client_cfg(host, port, method, password):
    return {
        "log": {"level": "error"},
        "inbounds": [{"type": "mixed", "tag": "in",
                      "listen": "127.0.0.1",
                      "listen_port": LOCAL_SOCKS_PORT}],
        "outbounds": [{"type": "shadowsocks", "tag": "out",
                       "server": host, "server_port": port,
                       "method": method, "password": password}],
    }


def check_tunnel(port=LOCAL_SOCKS_PORT, timeout=12):
    """(ok, reason): SOCKS5 handshake on 127.0.0.1:port + CONNECT probe
    through the Shadowsocks server. Pure stdlib."""
    import socket
    s = None
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")  # SOCKS5, no auth
        if s.recv(2) != b"\x05\x00":
            return False, "socks handshake rejected"
        host = b"www.gstatic.com"
        req = (b"\x05\x01\x00\x03" + bytes([len(host)]) + host +
               b"\x01\xbb")  # CONNECT host:443
        s.sendall(req)
        resp = s.recv(10)
        if len(resp) >= 2 and resp[1] == 0x00:
            return True, "traffic flows end-to-end"
        return False, f"socks CONNECT refused (code {resp[1] if resp else 'none'})"
    except Exception as e:
        return False, f"no traffic: {type(e).__name__}"
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def _usa_chrome_pids(profile):
    """PIDs of chrome.exe whose command line mentions our profile dir."""
    try:
        if os.name == "nt":
            marker = os.path.basename(os.path.abspath(profile))
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*" + marker + "*' } | "
                  "ForEach-Object { $_.ProcessId }")
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=20)
            return [p.strip() for p in (out.stdout or "").split()
                    if p.strip().isdigit()]
        else:
            out = subprocess.run(["pgrep", "-f", "chrome-usa"],
                                 capture_output=True, text=True, timeout=10)
            return [p.strip() for p in (out.stdout or "").split()
                    if p.strip().isdigit()]
    except Exception as e:
        slog(f"[chrome] stale-profile check skipped: {e}", flush=True)
        return []


def close_usa_chrome_graceful(profile, wait=10):
    """Close OUR usa-profile windows gently (lets Chrome flush logins,
    cookies and history to disk), force-kill only leftovers (usually
    headless stragglers with no window). Returns (graceful, forced)."""
    pids = _usa_chrome_pids(profile)
    if not pids:
        return 0, 0
    slog(f"[chrome] asking {len(pids)} USA window(s) to close gently ...",
         flush=True)
    try:
        if os.name == "nt":
            for pid in pids:
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive",
                         "-Command",
                         f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue)"
                         ".CloseMainWindow() | Out-Null"],
                        capture_output=True, timeout=10)
                except Exception:
                    pass
        else:
            for pid in pids:
                try:
                    subprocess.run(["kill", pid], capture_output=True,
                                   timeout=10)
                except Exception:
                    pass
    except Exception:
        pass
    graceful, forced = 0, 0
    try:
        left = pids
        for _ in range(max(1, int(wait))):
            time.sleep(1)
            left = _usa_chrome_pids(profile)
            if not left:
                break
        graceful = len(pids) - len(left)
        for pid in left:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=10)
                else:
                    subprocess.run(["kill", "-9", pid], capture_output=True,
                                   timeout=10)
                forced += 1
            except Exception:
                pass
    except Exception as e:
        slog(f"[chrome] close wait skipped: {e}", flush=True)
    if graceful or forced:
        slog(f"[chrome] closed gently: {graceful}, force-killed: {forced}.",
             flush=True)
        time.sleep(2)  # let file locks release before seeding
    return graceful, forced


def kill_stale_usa_chrome(profile):
    """Back-compat wrapper: gentle close first, force only leftovers."""
    g, f = close_usa_chrome_graceful(profile)
    return g + f


def profile_needs_seed(profile):
    """True only if the REAL Default/Preferences lacks our exact values.
    Steady-state launches return False -> no kill, no write, Chrome is
    never disturbed (logins/cookies/history stay intact)."""
    prefs = os.path.join(profile, "Default", "Preferences")
    try:
        with open(prefs, "r", encoding="utf-8") as f:
            cur = json.load(f) or {}
        intl = cur.get("intl") or {}
        web = cur.get("webrtc") or {}
        doh = cur.get("dns_over_https") or {}
        ok = (intl.get("accept_languages") == "en-US,en"
              and web.get("ip_handling_policy") == "disable_non_proxied_udp"
              and doh.get("mode") == "secure"
              and doh.get("templates") == "https://1.1.1.1/dns-query{?dns}")
        return not ok
    except Exception:
        return True  # missing/unreadable profile -> seed it


def seed_chrome_profile(profile):
    """Write privacy prefs into the USA profile BEFORE Chrome starts.

    Fully automatic (the app does it on every launch, no user steps):
    - Accept-Language en-US.
    - webrtc.ip_handling_policy = disable_non_proxied_udp, written to
      <profile>/Default/Preferences. That sub-path is what Chrome REALLY
      reads (v1.3.x wrote the parent dir's Preferences, which Chrome
      ignores -> the leak). Verified locally: with the policy in the
      real file, ICE gathering yields zero public candidates through
      our SOCKS tunnel (fail-closed, no real-IP srflx).
    - DNS-over-HTTPS "secure" so name resolution stays inside the
      encrypted stream (bore's TCP-only tunnel cannot carry plain UDP
      DNS; without DoH it would leak to the local ISP).
    Existing keys are preserved; call kill_stale_usa_chrome() first so a
    running USA window cannot overwrite the seed on exit.
    Returns True only if a read-back of the REAL file proves the policy.
    """
    prefs = os.path.join(profile, "Default", "Preferences")
    try:
        os.makedirs(os.path.join(profile, "Default"), exist_ok=True)
        if os.path.exists(prefs) and not profile_needs_seed(profile):
            slog("[chrome] profile already sealed - untouched (logins kept).",
                 flush=True)
            return True
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
        # Read-back from the file Chrome really uses (never trust the
        # write alone: a running Chrome would silently revert it).
        with open(prefs, "r", encoding="utf-8") as f:
            cur = json.load(f) or {}
        ok = (isinstance(cur.get("webrtc"), dict)
              and cur["webrtc"].get("ip_handling_policy")
              == "disable_non_proxied_udp")
        if not ok:
            slog("WARNING: WebRTC policy did not stick - leak test the "
                 "window before sensitive browsing!", flush=True)
        return ok
    except Exception as e:
        slog(f"Profile seed failed: {e}", flush=True)
        return False


def open_usa_chrome(chrome, url=None):
    """Open Chrome with a USA identity: English UI+content, no WebRTC leak.
    url is opened only when given (first run); otherwise a normal window."""
    profile = os.path.join(app_dir(), "chrome-usa")
    os.makedirs(profile, exist_ok=True)
    # Gentle order that preserves logins: seed (and any close) ONLY when
    # the profile actually lacks our values. Steady state = zero touching.
    if profile_needs_seed(profile):
        slog("[chrome] profile needs sealing - closing USA windows gently ...",
             flush=True)
        kill_stale_usa_chrome(profile)
        armed = seed_chrome_profile(profile)
    else:
        slog("[chrome] profile already sealed - reusing open windows as-is.",
             flush=True)
        armed = True
    # Read-back: prove what the profile will enforce (visible in terminal).
    try:
        with open(os.path.join(profile, "Default", "Preferences"),
                  "r", encoding="utf-8") as f:
            cur = json.load(f) or {}
        slog(f"WebRTC policy armed: {cur.get('webrtc', {}).get('ip_handling_policy')} | "
              f"DoH: {cur.get('dns_over_https', {}).get('mode')}" +
              ("" if armed else " | NOT VERIFIED - test the window!"),
              flush=True)
    except Exception:
        pass
    try:
        args = [
            chrome, f"--user-data-dir={profile}",
            f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
            "--lang=en-US",
            # Belt and suspenders next to the profile pref (the pref is
            # what provably closes the leak; the flag covers first-run
            # races). --disable-quic forces HTTP/3 to fall back to TCP
            # through the proxy: direct UDP 443 would bypass SOCKS and
            # expose the real IP to QUIC-capable sites.
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-quic"]
        if url:
            args.append(url)
        subprocess.Popen(args)
        slog("Chrome opened (USA profile: English, WebRTC leak blocked).",
              flush=True)
    except Exception as e:
        slog(f"Could not open Chrome: {e}", flush=True)


def run_terminal(cfg):
    """Terminal loop: show proxy address, refresh endpoint, open Chrome.
    Dual transport: ygg (mesh, stable, preferred) + bore (fallback).
    Every decision is logged literally ([net]/[ygg]/[bore]/[switch]/[check]).
    Raises RuntimeError if the repo/endpoint is unusable -> GUI reopens."""
    free_local_port()
    # NOTE: elevation happens in main() BEFORE any window (single UAC at
    # launch, single Start click). By the time we are here the process
    # is already elevated (or non-Windows). No second prompt, ever.
    exe = ensure_singbox()
    ygg_exe = ensure_yggdrasil()
    ygg_node = start_ygg_node(ygg_exe) if ygg_exe else None
    if ygg_node:
        up = ygg_peers_up(ygg_exe)
        slog(f"[ygg] mesh peerings up: {up if up >= 0 else 'unknown'} "
             f"(see ygg/ygg.log for detail).", flush=True)
    else:
        slog("[bore] ygg unavailable - bore only this session.", flush=True)
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
    transport = "bore"  # active leg; ygg takes over only after it PROVES itself
    ygg_proven = False  # set True on first end-to-end OK via mesh; reset on fail
    _ygg_probe_cool = 0.0  # next allowed background-probe timestamp
    cur = {"bore": "", "ygg": ""}
    logged = {"bore": "", "ygg": ""}  # last endpoint values already printed
    skip_logged = ""  # last bad endpoint we warned about (warn once)
    dead = 0
    _ygg_last_try = time.time()  # startup already tried once above
    _ygg_last_reach_log = 0.0  # throttle mesh-TCP FAIL logs (once/5min)
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

    def open_chrome_once():
        """Open the USA window exactly once - and ONLY on working traffic,
        so the user never faces a dead browser."""
        nonlocal chrome_opened
        if not chrome or chrome_opened:
            return
        chrome_opened = True
        if not cfg.get("welcomed"):
            open_usa_chrome(chrome, "https://ipleak.net/")
            cfg["welcomed"] = True
            save_config(cfg)
        else:
            open_usa_chrome(chrome)

    def switch_to(which, ep, why):
        """Rebuild local sing-box for (which, ep) and restart the tunnel."""
        nonlocal proc, tun_log, ygg_proven
        host, port = split_endpoint(ep)
        if not host or not port:
            slog(f"[switch] {why}: BAD endpoint '{ep}' - skipped.", flush=True)
            return False
        # Mesh pre-gate: never tear down a working tunnel for an
        # unroutable ghost IP. Raw TCP via the TUN must open first.
        if which == "ygg":
            _ok, _why = ygg_mesh_reachable(host, port)
            if not _ok:
                slog(f"[switch] ygg {ep}: skipped ({_why}) - bore untouched.",
                     flush=True)
                mark_bad(ep)
                return False
        ccfg = build_client_cfg(host, port, cfg.get("method", SS_METHOD),
                                cfg["password"])
        with open(client_cfg, "w", encoding="utf-8") as f:
            json.dump(ccfg, f)
        stop_tunnel(proc, tun_log)
        proc, tun_log = start_tunnel(exe, client_cfg)
        time.sleep(2)
        ok, reason = check_tunnel()
        planned = "planned, no downtime" if dead == 0 else "healing"
        slog(f"[switch] -> {which} {ep} ({why}; {planned}; "
              f"check: {'OK' if ok else 'FAIL: ' + reason}).", flush=True)
        if ok:
            _bad_until.pop(ep, None)  # forgiven: it works
            if which == "ygg":
                ygg_proven = True
                slog("[ygg] mesh leg PROVEN - real traffic flows.", flush=True)
        else:
            mark_bad(ep)  # don't chase it again until cooldown expires
            if which == "ygg":
                ygg_proven = False
        return ok

    try:
        while True:
            # ---- 1) fresh endpoints, literally logged on change ----
            name_b, bore_ep = fetch_endpoint(cfg)
            # Instant path: while the tunnel is down the branch raw URL can
            # lag ~5 min (CDN cache), so ask the commits API for the fresh
            # SHA (throttled, ~90s) and jump straight to the new endpoint.
            if dead and bore_ep == cur["bore"]:
                _pn, _pe = fetch_pinned_endpoint(cfg)
                if _pe and _pe != cur["bore"]:
                    slog(f"[net] bore endpoint via SHA-pin (CDN was stale): {_pe}",
                         flush=True)
                    name_b, bore_ep = _pn, _pe
            if bore_ep != logged["bore"]:
                logged["bore"] = bore_ep
                slog(f"[net] bore endpoint: '{cur['bore'] or 'none'}' -> "
                     f"'{bore_ep or 'none'}' (source: {name_b or 'unpublished'}).",
                     flush=True)
            name_y, ygg_ep = ("", "")
            if ygg_node and ygg_node.poll() is None:
                name_y, ygg_ep = fetch_ygg_endpoint(cfg)
                # Same CDN staleness applies to the mesh file: pin it while down.
                if dead and ygg_ep == cur["ygg"]:
                    _pn, _pe = fetch_pinned_ygg(cfg)
                    if _pe and _pe != cur["ygg"]:
                        slog(f"[net] ygg endpoint via SHA-pin (CDN was stale): {_pe}",
                             flush=True)
                        name_y, ygg_ep = "ss_ygg_url.txt", _pe
                if ygg_ep != logged["ygg"]:
                    logged["ygg"] = ygg_ep
                    slog(f"[net] ygg endpoint: '{cur['ygg'] or 'none'}' -> "
                         f"'{ygg_ep or 'none'}'.", flush=True)
            elif ygg_exe:
                _now = time.time()
                if _now - _ygg_last_try > 120:
                    _ygg_last_try = _now
                    slog("[ygg] node process gone - restarting it ...",
                         flush=True)
                    ygg_node = start_ygg_node(ygg_exe)
                    if not ygg_node:
                        slog("[ygg] restart failed - bore only for now.",
                             flush=True)
            # ---- 2) desired leg: ygg ONLY after it proves real traffic ----
            # The old logic ("ygg whenever its file exists") tore down a
            # working bore tunnel to chase ghost mesh IPs - every failed
            # attempt = ~4s downtime + flip-flop storms. Now: bore serves
            # until a background probe on port 1089 proves the mesh leg
            # end-to-end; only then does ygg become desired.
            # Adopt the freshest known values silently for the IDLE leg, so
            # failover always jumps to something current (and the [net] log
            # above fires once per real change instead of every loop).
            # Gated on proc: before the first tunnel exists cur must stay
            # empty, otherwise the initial switch is suppressed (want ==
            # cur) and the healing check fires against an empty port.
            if proc is not None:
                if bore_ep:
                    cur["bore"] = bore_ep
                if ygg_ep:
                    cur["ygg"] = ygg_ep
            if ygg_ep and (ygg_proven or transport == "ygg"):
                desired = "ygg"
            elif ygg_ep and transport == "bore" and not ygg_proven \
                    and not is_bad(ygg_ep) and dead == 0 \
                    and proc is not None \
                    and time.time() >= _ygg_probe_cool:
                # Background probe: temp sing-box on 1089, live bore on
                # 1080 untouched. Throttled to once/60s.
                _ygg_probe_cool = time.time() + 60
                _yh, _yp = split_endpoint(ygg_ep)
                if _yh and _yp:
                    _rok, _rwhy = ygg_mesh_reachable(_yh, _yp)
                    if not _rok:
                        # Mesh TCP timeout has TWO very different causes:
                        # (a) route not converged yet -> retry later, or
                        # (b) the file points at a DEAD server generation
                        # (stale CDN / handover race) -> no amount of
                        # waiting helps. Distinguish via SHA-pin (throttled
                        # ~90s, immutable raw URL bypasses the branch cache):
                        # a different pinned endpoint means (b).
                        _pn2, _pe2 = fetch_pinned_ygg(cfg)
                        if _pe2 and _pe2 != ygg_ep:
                            slog(f"[ygg-probe] endpoint STALE (file: {ygg_ep} "
                                 f"-> live: {_pe2}) - adopting live value.",
                                 flush=True)
                            cur["ygg"] = _pe2
                            ygg_ep = _pe2
                            _yh, _yp = split_endpoint(ygg_ep)
                            if _yh and _yp:
                                _rok, _rwhy = ygg_mesh_reachable(_yh, _yp)
                                slog(f"[ygg-probe] live endpoint mesh TCP: "
                                     f"{'open' if _rok else 'FAIL (' + _rwhy + ')'}.",
                                     flush=True)
                        if not _rok and time.time() - _ygg_last_reach_log > 300:
                            _ygg_last_reach_log = time.time()
                            slog(f"[ygg-probe] mesh TCP {ygg_ep}: FAIL "
                                 f"({_rwhy}) - bore serves, retry later.",
                                 flush=True)
                    else:
                        slog(f"[ygg-probe] mesh TCP open, testing traffic "
                             f"via probe (bore untouched) ...", flush=True)
                        _pok, _pwhy = probe_ygg_leg(
                            exe, _yh, _yp, cfg.get("method", SS_METHOD),
                            cfg["password"])
                        slog(f"[ygg-probe] {'OK - promoting mesh leg' if _pok else 'FAIL: ' + _pwhy + ' - bore serves'}.",
                             flush=True)
                        if _pok:
                            ygg_proven = True
                            _bad_until.pop(ygg_ep, None)
                        else:
                            mark_bad(ygg_ep)
                # Promote at once when the probe just proved the leg;
                # otherwise keep serving bore this round.
                desired = "ygg" if ygg_proven else "bore"
            elif ygg_ep and transport == "ygg":
                desired = "ygg"  # already on mesh: stay, healing decides
            else:
                desired = "bore" if bore_ep else ("ygg" if ygg_ep else "bore")
            want = {"bore": bore_ep, "ygg": ygg_ep}[desired]
            if not want:
                fails += 1
                slog(f"[net] no usable endpoint ({fails}) - next check soon. "
                     f"Follow https://github.com/{cfg['owner']}/{cfg['repo']}/actions",
                     flush=True)
                if fails >= 10:
                    raise RuntimeError("No endpoint published. Re-enter the repo URL.")
                time.sleep(60)
                continue
            fails = 0
            # ---- 3) switch when leg or endpoint changed ----
            # Hysteresis: never jump into an endpoint that failed minutes
            # ago (two server generations flip-flopping the same file would
            # otherwise bounce us dead-alive-dead). Adopt silently instead.
            do_switch = True
            if (desired != transport or want != cur[transport]) \
                    and is_bad(want):
                if want != skip_logged:
                    skip_logged = want
                    left = int(_bad_until.get(want, 0) - time.time())
                    slog(f"[net] {desired} endpoint {want} failed recently - "
                         f"skipping switch for ~{max(left, 0)}s (staying on "
                         f"{transport}; will retry automatically).", flush=True)
                cur[desired] = want  # adopt quietly, log once
                do_switch = False
            if do_switch and (desired != transport or want != cur[transport]):
                if desired != transport:
                    why = (f"prefer {desired} ("
                           + ("ygg proven, stable" if desired == "ygg"
                              else "ygg missing, bore fallback") + ")")
                else:
                    why = f"{transport} endpoint renewed"
                transport = desired
                cur[desired] = want
                if want == skip_logged:
                    skip_logged = ""  # retrying it now: future skips re-log
                alive = switch_to(desired, want, why)
                if first_run and not alive:
                    slog("[net] proxy not responding on startup - server "
                         "self-heals, following its fresh endpoint ...",
                         flush=True)
                    slog("[chrome] window held until traffic flows "
                         "(no dead browser).", flush=True)
                if alive:
                    open_chrome_once()
                slog("-" * 60)
                slog(f"PROXY ADDRESS (manual use): 127.0.0.1:{LOCAL_SOCKS_PORT} (SOCKS5 + HTTP)")
                slog(f"SERVER: {want} "
                      f"({'mesh-ygg' if desired == 'ygg' else 'encrypted-bore'}) "
                      f"[leg: {transport}]")
                slog("IP: USA (Phoenix, Arizona)")
                slog("-" * 60, flush=True)
                if alive:
                    open_chrome_once()
                elif chrome and chrome_opened:
                    slog("Endpoint renewed - using the already-open Chrome "
                          "window (no new window).", flush=True)
                first_run = False
            if proc and proc.poll() not in (None, 0):
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                slog(f"[tunnel] local sing-box died - restarted on {transport}.",
                     flush=True)
            # --- client-side healing: does traffic REALLY flow? ---
            # (TCP to bore.pub is not enough: the tunnel can be up while
            # the server-side proxy refuses everything -> ERROR flood.)
            if cur[transport]:
                ok, reason = check_tunnel()
                # Literal visibility: every failure and every recovery logged.
                if not ok and (dead == 0 or (dead + 1) % 3 == 0):
                    slog(f"[check] {transport} via 127.0.0.1:{LOCAL_SOCKS_PORT}: "
                         f"FAIL ({reason}) - dead streak {dead + 1}.", flush=True)
                if ok:
                    if dead:
                        slog("[check] traffic flows again.", flush=True)
                    dead = 0
                    _bad_until.pop(cur[transport], None)
                    open_chrome_once()  # deferred open fires here
                else:
                    dead += 1
                    # Instant failover: the other leg may already be fine.
                    other = "ygg" if transport == "bore" else "bore"
                    if cur[other]:
                        slog(f"[failover] {transport} dead - trying {other} "
                             f"{cur[other]} now ...", flush=True)
                        # Leaving a dead mesh leg: it must RE-prove itself
                        # via background probe before taking over again -
                        # otherwise the next loop would jump straight back
                        # into the same dead endpoint.
                        if transport == "ygg":
                            ygg_proven = False
                        transport = other
                        if switch_to(other, cur[other], "failover"):
                            dead = 0
                    elif transport == "ygg":
                        ygg_proven = False
                    # Follow-only: the workflow heals itself on FIRST failure and
                    # publishes a new endpoint; the loop above picks it up.
            # Poll fast while down (5s) so the switch is instant, calm (15s)
            # while healthy. Raw polling is free; the API stays throttled.
            time.sleep(5 if dead else 15)
    except KeyboardInterrupt:
        slog("\nStopping...")
    finally:
        stop_tunnel(proc, tun_log)
        stop_ygg_node()


def main():
    if "--reset" in sys.argv:
        try:
            os.remove(config_path())
        except Exception:
            pass
    # Elevation FIRST, before ANY window (Windows): the mesh leg needs
    # the TUN interface, which Windows only grants elevated. Flow:
    #   double-click -> console asks for admin -> UAC pops ->
    #   Allow: the elevated copy continues into setup (ONE Start click);
    #          this window closes itself.
    #   Deny:  the program EXITS (no half-running copy without mesh).
    if os.name == "nt" and not is_admin() and not ELEVATED:
        slog("[admin] IPNET needs administrator (mesh driver) - "
             "one UAC click ...", flush=True)
        launched = try_elevate("startup")
        if launched:
            slog("[admin] elevated copy starting - this window closes.",
                 flush=True)
        else:
            slog("[admin] elevation declined - exiting.", flush=True)
        try:
            input("Press Enter to close ...")
        except Exception:
            pass
        sys.exit(0 if launched else 1)
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
