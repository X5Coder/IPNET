#!/usr/bin/env python3
"""
IPNET - one-click USA proxy.
Single EXE distributed via GitHub Releases.

Each launch shows the same simple window:
  1. Paste your proxy repo link (public, or private + token below).
  2. Press Start.
The app pulls the live tunnel address + user ID from the repo files (no
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
APP_VERSION = "v3.5.0"
TEMPLATE_URL = "https://github.com/X5Coder/IPNET"
APP_AUTHOR = "X5Coder"
RAW = "https://raw.githubusercontent.com"
SB_VERSION = "1.14.2"
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


# (Cloudflare era: no admin rights needed - plain user launch. The old
# elevation flow and the whole Yggdrasil transport were removed in v2.0.0.)


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
        if cfg.get("owner") and cfg.get("repo") and cfg.get("uuid"):
            return cfg
        # Migrate pre-v2 configs (password-based) -> re-attach needed.
        if cfg.get("owner") and cfg.get("repo") and cfg.get("password") \
                and not cfg.get("uuid"):
            return None
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


def extract_uuid_from_repo_text(singbox_text=""):
    """Extract the VMess user UUID from singbox-server.json (public file).
    Returns uuid string or ''."""
    if singbox_text:
        try:
            data = json.loads(singbox_text)
            for inbound in data.get("inbounds", []):
                for u in inbound.get("users", []):
                    if u.get("uuid"):
                        return u["uuid"]
        except Exception:
            pass
        m = re.search(r'"uuid"\s*:\s*"([0-9a-fA-F-]{36})"', singbox_text)
        if m:
            return m.group(1)
    return ""


# Shared proxy login for every Render deploy (public-proxy design:
# same idea as the shared Worker uuid — zero config for beginners).
RENDER_USER = "x5coder"
RENDER_PASS = "X5_Usa_2026_Secure!"


def _valid_render_host(v):
    """'xxx.onrender.com' -> itself or ''. v3.5: Render free web service
    (Oregon = US) running server.py — real TCP sockets, works on free plan."""
    v = (v or "").strip().lower()
    v = re.sub(r"^https?://", "", v).split("/")[0].split(":")[0]
    return v if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.onrender\.com$", v) else ""


def _valid_worker_host(v):
    """'xxx.workers.dev' -> itself or ''. New in v3: the endpoint is the
    user's OWN Cloudflare Worker hostname (worker.txt, written once),
    not a trycloudflare tunnel rewritten every minute (that spam is what
    got fresh accounts banned)."""
    v = (v or "").strip().lower()
    v = re.sub(r"^https?://", "", v).split("/")[0]
    return v if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.workers\.dev$", v) else ""


def _valid_cf_host(v):
    # Back-compat alias: old cf_vmess.txt hostnames still accepted if seen.
    v = (v or "").strip().lower()
    if re.match(r"^[a-z0-9-]+\.trycloudflare\.com$", v):
        return v
    return _valid_worker_host(v)


def fetch_public_repo_snapshot(owner, repo):
    """Read-only check of a PUBLIC repo (no login). Returns
    {endpoint, endpoint_file, uuid, has_code, mode}.
    v3.5: Render FIRST (render.txt = xxx.onrender.com running server.py,
    real CONNECT proxy on 443 through Render TLS), Worker second
    (worker.txt), legacy cf_vmess.txt last. Repo link is still the ONLY
    input — endpoint files are written once, never every minute."""
    base = f"{RAW}/{owner}/{repo}/main"
    endpoint = _valid_render_host(raw_get(f"{base}/render.txt", bust=True))
    endpoint_file = "render.txt" if endpoint else ""
    mode = "render" if endpoint else ""
    if not endpoint:
        endpoint = _valid_worker_host(raw_get(f"{base}/worker.txt", bust=True))
        endpoint_file = "worker.txt" if endpoint else ""
        mode = "worker" if endpoint else ""
    if not endpoint:
        endpoint = _valid_cf_host(raw_get(f"{base}/cf_vmess.txt", bust=True))
        endpoint_file = "cf_vmess.txt" if endpoint else ""
    singbox_text = raw_get(f"{base}/singbox-server.json", bust=True)
    workflow_text = raw_get(f"{base}/.github/workflows/proxy.yml", bust=True)
    has_code = bool(singbox_text or workflow_text)
    uuid = extract_uuid_from_repo_text(singbox_text)
    return {"endpoint": endpoint, "endpoint_file": endpoint_file,
            "uuid": uuid, "has_code": has_code, "mode": mode}


def setup_attach(repo_text, log):
    """Follow-only attach (public repos only, no login, no token).
    v3.5: repo link ONLY — endpoint comes from render.txt (Render Oregon,
    preferred) or worker.txt (Worker fallback), written once. No second
    field, no override.
    Raises RuntimeError with a plain message when there is nothing
    usable yet (wrong link / action not finished yet / code missing)."""
    parsed = parse_repo_url(repo_text or "")
    if not parsed:
        raise RuntimeError("Paste a repo link, e.g. https://github.com/YOU/my-proxy")
    owner, repo = parsed
    log(f"Checking {owner}/{repo} ...")
    snap = fetch_public_repo_snapshot(owner, repo)
    if not snap["has_code"]:
        raise RuntimeError("No proxy code in this repo yet. Create it from the "
                           "template first (Step 1), then paste its link here.")
    if not snap["uuid"]:
        raise RuntimeError("Code found but user ID unreadable - recreate from template.")
    cfg = {"owner": owner, "repo": repo, "uuid": snap["uuid"],
           "attached": True, "readonly": True}
    cfg.pop("worker_host", None)  # v3.3: no override field anymore
    save_config(cfg)
    if snap["endpoint"]:
        log(f"Attached! Server: {snap['endpoint']}")
        return cfg
    # Action not finished yet: WAIT here with live progress, so Start
    # only finishes when render.txt / worker.txt is published.
    log("Waiting for the setup action (paste render.txt, then watch Actions) ...")
    started = time.time()
    for _i in range(48):
        time.sleep(15)
        v = _valid_render_host(
            raw_get(f"{RAW}/{owner}/{repo}/main/render.txt", bust=True))
        if not v:
            v = _valid_worker_host(
                raw_get(f"{RAW}/{owner}/{repo}/main/worker.txt", bust=True))
        if not v:
            v = _valid_cf_host(
                raw_get(f"{RAW}/{owner}/{repo}/main/cf_vmess.txt", bust=True))
        if v:
            log(f"Ready! Tunnel: {v}")
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


def fetch_pinned_cf(cfg):
    """Fresh tunnel hostname via SHA-pinned raw URL (bypasses the ~5min
    branch CDN cache). Returns ('cf_vmess.txt', 'host') or ('','').
    Throttled to ~90s per path (unauthenticated API limit)."""
    global _last_seen_sha
    path = "cf_vmess.txt"
    sha = _api_latest_sha(cfg["owner"], cfg["repo"], path)
    if not sha or sha == _last_seen_sha.get(path, ""):
        return "", ""
    v = _valid_cf_host(raw_get(
        f"{RAW}/{cfg['owner']}/{cfg['repo']}/{sha}/{path}", timeout=15))
    _last_seen_sha[path] = sha
    return (path, v) if v else ("", "")


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


def _lock_path():
    try:
        return os.path.join(app_dir(), "app.lock")
    except Exception:
        return None


def _pid_alive(pid):
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=15)
            return str(pid) in (out.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _release_own_lock():
    """Remove app.lock, but only if WE own it."""
    try:
        lp = _lock_path()
        if lp and os.path.exists(lp) and \
                (open(lp, "r", encoding="utf-8").read()
                 or "").strip().split("|")[0] == str(os.getpid()):
            os.remove(lp)
    except Exception:
        pass


def single_instance_guard():
    """One manager per machine, newest wins, no wars, no prompts.

    Background: duplicate managers fight over port 1080 and kill each
    other's tunnels, so both flap forever. Now:
      - same version already running -> this copy exits quietly;
      - older/different version (or lockless legacy copy) running ->
        it is closed once (upgrade takeover) and this copy proceeds;
      - stale lock (dead PID) -> adopted silently.
    Runs FIRST in main(), before any window."""
    lp = _lock_path()
    me = os.getpid()
    if not lp:
        return
    import atexit

    def _release():
        _release_own_lock()

    def _read_lock():
        try:
            if os.path.exists(lp):
                parts = (open(lp, "r", encoding="utf-8").read()
                         or "").strip().split("|")
                if parts and parts[0].strip().isdigit():
                    ver = parts[1].strip() if len(parts) > 1 else ""
                    return int(parts[0].strip()), ver
        except Exception:
            pass
        return None, ""

    def _take():
        try:
            with open(lp, "w", encoding="utf-8") as f:
                f.write(f"{me}|{APP_VERSION}")
            atexit.register(_release)
        except Exception:
            pass

    def _close(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    lock_pid, lock_ver = _read_lock()
    if lock_pid and lock_pid != me and _pid_alive(lock_pid):
        if lock_ver == APP_VERSION:
            slog(f"IPNET {APP_VERSION} is already running (pid {lock_pid}) - "
                 f"exiting. (One copy only.)",
                 flush=True)
            try:
                input("Press Enter to close ...")
            except Exception:
                pass
            sys.exit(0)
        slog(f"[mgr] taking over from older {lock_ver or 'unknown'} "
             f"(pid {lock_pid}) ...", flush=True)
        _close(lock_pid)
        time.sleep(3)
    # No live lock: pre-mutex copies (v1.6.2 and older) never wrote one.
    # The startup sweep below closes them once; this guard then owns it.
    _take()


def kill_other_managers():
    """Single-manager guard: never share the machine with another copy.

    Two IPNET managers fight over port 1080, so both tunnels flap and
    the log fills with 'died - restarted'. The NEW copy wins: any other
    IPNET* binary, or any python running THIS script (except this
    process), is closed first. Runs ONCE at startup, never in-loop."""
    if os.name != "nt":
        return
    me = os.getpid()
    try:
        script = os.path.basename(os.path.abspath(__file__))
        pat = re.compile(r"[\\/]" + re.escape(script) + r"(?=[\"'\s]|$)",
                         re.IGNORECASE)
    except Exception:
        return
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -like "
             "'IPNET*' -or $_.Name -eq 'python.exe' -or $_.Name -eq "
             "'pythonw.exe' } | ForEach-Object { \"{0}|{1}|{2}\" -f "
             "$_.ProcessId, $_.Name, $_.CommandLine }"],
            capture_output=True, text=True, timeout=30)
    except Exception as e:
        slog(f"[mgr] single-instance scan skipped: {e}", flush=True)
        return
    for line in (out.stdout or "").splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) != 3:
            continue
        pid_s, name, cmd = parts
        if not pid_s.strip().isdigit():
            continue
        pid = int(pid_s.strip())
        if pid == me:
            continue
        nl = name.strip().lower()
        # Frozen copies match by name; script copies match only when OUR
        # file is the actual script (path separator required, so a mere
        # mention inside some -c snippet never matches).
        mine = nl.startswith("ipnet") or (
            nl.startswith("python") and bool(pat.search(cmd or "")))
        if not mine:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
            slog(f"[mgr] closed duplicate manager: {name.strip()}({pid}) "
                 f"- single copy from here.", flush=True)
        except Exception:
            slog(f"[mgr] could not close {name.strip()}({pid}) - close it "
                 f"manually (Task Manager as admin).", flush=True)
    time.sleep(3)  # let ports settle before binding


def build_client_cfg(host, uuid, mode="worker"):
    """Local sing-box: mixed inbound on 1080.
    mode=render: HTTP outbound through YOUR Render service
    (server.py CONNECT proxy, TLS on 443, shared user/pass).
    mode=worker: VLESS+WS+TLS outbound through your Worker (legacy)."""
    if mode == "render":
        import base64
        auth = base64.b64encode(
            f"{RENDER_USER}:{RENDER_PASS}".encode()).decode()
        return {
            "log": {"level": "error"},
            "inbounds": [{"type": "mixed", "tag": "in",
                          "listen": "127.0.0.1",
                          "listen_port": LOCAL_SOCKS_PORT}],
            "outbounds": [{"type": "http", "tag": "out",
                           "server": host, "server_port": 443,
                           "username": RENDER_USER, "password": RENDER_PASS,
                           "tls": {"enabled": True, "server_name": host}}],
        }
    return {
        "log": {"level": "error"},
        "inbounds": [{"type": "mixed", "tag": "in",
                      "listen": "127.0.0.1",
                      "listen_port": LOCAL_SOCKS_PORT}],
        "outbounds": [{"type": "vless", "tag": "out",
                       "server": host, "server_port": 443,
                       "uuid": uuid,
                       "tls": {"enabled": True, "server_name": host},
                       "transport": {"type": "ws", "path": "/ipnet",
                                     "headers": {"Host": host}}}],
    }


def tunnel_http_status(port=LOCAL_SOCKS_PORT, timeout=10):
    """HTTP status of http://httpbin.org/ip through the tunnel (SOCKS5).
    Returns int status or -1. Spots edge rate-limiting (HTTP 429 from
    the quick-tunnel concurrency cap) that a bare CONNECT check cannot
    see. Pure stdlib."""
    import socket
    s = None
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00":
            return -1
        host = b"httpbin.org"
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host + b"\x00\x50")
        if s.recv(10)[1] != 0x00:
            return -1
        s.sendall(b"GET /ip HTTP/1.1\r\nHost: httpbin.org\r\n"
                  b"Connection: close\r\n\r\n")
        data = b""
        while b"\r\n" not in data and len(data) < 4096:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk
        m = re.search(rb"HTTP/1\.[01]\s+(\d{3})", data)
        return int(m.group(1)) if m else -1
    except Exception:
        return -1
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def fetch_geo_via_tunnel(port=LOCAL_SOCKS_PORT, timeout=10):
    """(country, city, ip) as seen through the tunnel, or fallbacks.
    Shown once per successful switch so the user SEES where they exit.
    Pure stdlib."""
    import socket
    s = None
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00":
            return "USA", "", ""
        host = b"ipinfo.io"
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host + b"\x00\x50")
        if s.recv(10)[1] != 0x00:
            return "USA", "", ""
        s.sendall(b"GET /json HTTP/1.1\r\nHost: ipinfo.io\r\n"
                  b"Connection: close\r\nUser-Agent: IPNET\r\n\r\n")
        data = b""
        while len(data) < 8192:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        body = data.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in data else b""
        info = json.loads(body.decode("utf-8", "ignore") or "{}")
        return (info.get("country", "USA") or "USA",
                info.get("city", "") or "", info.get("ip", "") or "")
    except Exception:
        return "USA", "", ""
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def check_tunnel(port=LOCAL_SOCKS_PORT, timeout=12):
    """(ok, reason): SOCKS5 handshake on 127.0.0.1:port + CONNECT probe
    through the tunnel server. Pure stdlib."""
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
      encrypted stream instead of leaking to the local ISP.
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
        # DNS-over-HTTPS through the proxy (keeps name resolution inside
        # the encrypted stream, never leaking to the local ISP).
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
    """Terminal loop: single cloudflared transport (VMess+WS+TLS).
    Show proxy address, follow the tunnel hostname, open Chrome only on
    working traffic. Every decision is logged literally
    ([net]/[cf]/[switch]/[check]).
    Raises RuntimeError if the repo/endpoint is unusable -> GUI reopens."""
    free_local_port()
    exe = ensure_singbox()
    if not cfg.get("uuid"):
        raise RuntimeError("Missing user ID - re-enter the repo URL.")
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
    cur = ""  # active tunnel hostname ('' = no tunnel yet)
    logged_ep = ""  # last hostname value already printed
    skip_logged = ""  # last bad hostname we warned about (warn once)
    dead = 0
    _http_tick = 0  # HTTP-429 radar counter (see healing block)
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

    def switch_to(host, why, mode="worker"):
        """Rebuild local sing-box for the hostname and restart."""
        nonlocal proc, tun_log
        if not host:
            slog(f"[switch] {why}: BAD hostname - skipped.", flush=True)
            return False
        ccfg = build_client_cfg(host, cfg["uuid"], mode=mode)
        with open(client_cfg, "w", encoding="utf-8") as f:
            json.dump(ccfg, f)
        stop_tunnel(proc, tun_log)
        proc, tun_log = start_tunnel(exe, client_cfg)
        time.sleep(2)
        if proc.poll() is not None:
            # Died at once (a second manager squatting :1080 is the
            # classic): dump the tunnel-log tail so the cause is
            # visible instead of looping blind.
            try:
                with open(tunnel_log_path(), "r", encoding="utf-8",
                          errors="ignore") as _lf:
                    _tail = _lf.read()[-400:]
                slog(f"[switch] cf tunnel died at once "
                     f"(exit {proc.poll()}); log tail: {_tail}", flush=True)
            except Exception:
                slog(f"[switch] cf tunnel died at once "
                     f"(exit {proc.poll()}).", flush=True)
            mark_bad(host)
            return False
        # 30s cap (not the 12s default): the first dial through a fresh
        # tunnel needs TLS+WS setup; steady-state checks answer in <2s.
        ok, reason = check_tunnel(timeout=30)
        planned = "planned, no downtime" if dead == 0 else "healing"
        slog(f"[switch] -> cf {host} ({why}; {planned}; "
              f"check: {'OK' if ok else 'FAIL: ' + reason}).", flush=True)
        if ok:
            _bad_until.pop(host, None)  # forgiven: it works
            slog("[cf] tunnel live - real traffic flows.", flush=True)
        else:
            mark_bad(host)  # don't chase it again until cooldown expires
        return ok

    try:
        while True:
            # v3.5: Render (render.txt) FIRST, Worker second, legacy last.
            r_host = _valid_render_host(raw_get(
                f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/render.txt",
                bust=True))
            if r_host:
                cf_host, cf_mode = r_host, "render"
            else:
                cf_host = _valid_worker_host(raw_get(
                    f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/worker.txt",
                    bust=True))
                cf_mode = "worker" if cf_host else ""
            if not cf_host:
                # legacy installs still publishing cf_vmess.txt
                cf_host = _valid_cf_host(raw_get(
                    f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/cf_vmess.txt",
                    bust=True))
            # Instant path: while the tunnel is down the branch raw URL can
            # lag ~5 min (CDN cache), so ask the commits API for the fresh
            # SHA (throttled, ~90s) and jump straight to the new hostname.
            if dead and cf_host == cur:
                _pn, _pe = fetch_pinned_cf(cfg)
                if _pe and _pe != cur:
                    slog(f"[net] tunnel via SHA-pin (CDN was stale): {_pe}",
                         flush=True)
                    cf_host = _pe
            if cf_host != logged_ep:
                logged_ep = cf_host
                slog(f"[net] tunnel: '{cur or 'none'}' -> "
                     f"'{cf_host or 'none'}'.", flush=True)
            if not cf_host:
                fails += 1
                slog(f"[net] no tunnel published ({fails}) - next check soon. "
                     f"Follow https://github.com/{cfg['owner']}/{cfg['repo']}/actions",
                     flush=True)
                if fails >= 10:
                    raise RuntimeError("No tunnel published. Re-enter the repo URL.")
                time.sleep(60)
                continue
            fails = 0
            # ---- 2) switch when the tunnel hostname changed ----
            # Hysteresis: never jump into a hostname that failed minutes
            # ago. Wait out the cooldown instead (the loop retries
            # automatically when it expires).
            if cf_host != cur:
                if is_bad(cf_host):
                    if cf_host != skip_logged:
                        skip_logged = cf_host
                        left = int(_bad_until.get(cf_host, 0) - time.time())
                        slog(f"[net] tunnel {cf_host} failed recently - "
                             f"retrying in ~{max(left, 0)}s.", flush=True)
                else:
                    cur = cf_host
                    if cf_host == skip_logged:
                        skip_logged = ""  # retrying it now
                    alive = switch_to(cf_host, "server renewed"
                                      if not first_run else "initial connect",
                                      mode=(cf_mode or "worker"))
                    if first_run and not alive:
                        slog("[net] tunnel not reachable on startup - "
                             "following its fresh hostname ...", flush=True)
                        slog("[chrome] window held until traffic flows "
                             "(no dead browser).", flush=True)
                    if alive:
                        open_chrome_once()
                        _cc, _city, _ip = fetch_geo_via_tunnel()
                        slog("=" * 60)
                        slog("  PROXY CONNECTED")
                        slog(f"  Country : {_cc}" + (f" ({_city})" if _city else ""))
                        slog(f"  Your IP : {_ip or 'checking...'}  (verify: https://ipleak.net/)")
                        slog(f"  Server  : {cf_host}  (Render Oregon USA, HTTP+TLS)" if (cf_mode or "") == "render" else f"  Server  : {cf_host}  (Cloudflare worker, VLESS+WS+TLS)")
                        slog(f"  Local   : 127.0.0.1:{LOCAL_SOCKS_PORT}  (SOCKS5 + HTTP - use in any app)")
                        slog(f"  Repo    : {cfg['owner']}/{cfg['repo']}")
                        slog("=" * 60, flush=True)
                    else:
                        slog(f"[net] switch to {cf_host} failed - retrying automatically.",
                             flush=True)
                    if not alive and chrome and chrome_opened:
                        slog("Endpoint renewed - using the already-open Chrome "
                              "window (no new window).", flush=True)
                    if alive or proc is not None:
                        first_run = False
            if proc and proc.poll() not in (None, 0):
                _code = proc.poll()
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                slog(f"[tunnel] local sing-box died (exit {_code}) - "
                     f"restarted on cf.", flush=True)
            # --- healing: does traffic REALLY flow through the tunnel? ---
            # (Gated on a live tunnel: before the first switch there is
            # nothing on :1080, and a phantom check would only paint a
            # bogus dead streak.)
            if cur and proc is not None and proc.poll() is None:
                ok, reason = check_tunnel()
                # Literal visibility: every failure and every recovery logged.
                if not ok and (dead == 0 or (dead + 1) % 3 == 0):
                    slog(f"[check] cf via 127.0.0.1:{LOCAL_SOCKS_PORT}: "
                         f"FAIL ({reason}) - dead streak {dead + 1}.", flush=True)
                if ok:
                    if dead:
                        slog("[check] traffic flows again.", flush=True)
                    dead = 0
                    _bad_until.pop(cur, None)
                    open_chrome_once()  # deferred open fires here
                    # Edge-cap radar: a bare CONNECT cannot see HTTP 429
                    # (quick-tunnel concurrency cap), so sample a real HTTP
                    # status every ~4th healthy loop. On 429 the server is
                    # already rotating - go fast-poll to follow it at once.
                    _http_tick += 1
                    if _http_tick >= 4:
                        _http_tick = 0
                        if tunnel_http_status() == 429:
                            slog("[check] edge rate limit (HTTP 429) - "
                                 "server is rotating, following ...", flush=True)
                            dead = 1
                else:
                    dead += 1
                    # No fallback exists: keep polling fast so a republished
                    # hostname is picked up at once (the fetch above +
                    # SHA-pin do the healing).
            # Poll fast while down (5s) so recovery is instant, calm (15s)
            # while healthy. Raw polling is free; the API stays throttled.
            time.sleep(5 if dead else 15)
    except KeyboardInterrupt:
        slog("\nStopping...")
    finally:
        stop_tunnel(proc, tun_log)


def main():
    # Single instance FIRST (before reset/windows): a second copy exits
    # quietly here - no prompts, no tunnel wars.
    single_instance_guard()
    if "--reset" in sys.argv:
        try:
            os.remove(config_path())
        except Exception:
            pass
    # No admin rights needed (cloudflared era): plain launch, single
    # Start click, no UAC. One manager per machine.
    kill_other_managers()
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
