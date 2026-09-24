#!/usr/bin/env python3
"""
IPNET - one-click USA proxy.
Single EXE distributed via GitHub Releases.

First launch: a very simple window explains (in English) what to do:
  1. Create a free GitHub account
  2. Create a new PUBLIC empty repository
  3. Create a token, paste the repo URL + token, press Start
The app then automatically: uploads the server project to your repo,
starts the GitHub Action, waits for the encrypted endpoint, saves
everything, starts the local tunnel and opens Chrome through the USA IP.

Every next launch: a terminal window shows the proxy address, refreshes
the newest IP/endpoint automatically and opens Chrome. If the repo is
missing or anything breaks, the setup window opens again asking for the
repo URL.

Windows: config at %APPDATA%/IPNET/config.json (chosen at setup).
Needs on PC: internet + Chrome. No git needed (uses GitHub API).
"""
import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile

APP_NAME = "IPNET"
APP_VERSION = "v1.0.1"
CANONICAL_REPO = "X5Coder/proxy-usa"  # templates are downloaded from here
PROJECT_FILES = [
    "server.py",
    "singbox-server.json",
    ".github/workflows/proxy.yml",
    "ss-client-template.json",
    ".gitignore",
    "USER_README.md",  # uploaded as README.md (credits + channel button)
]
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
SB_VERSION = "1.14.2"
GH_VERSION = "2.101.0"
SS_METHOD = "aes-256-gcm"
LOCAL_SOCKS_PORT = 1080


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


def bin_dir():
    d = os.path.join(app_dir(), "bin")
    os.makedirs(d, exist_ok=True)
    return d


def profile_dir():
    d = os.path.join(app_dir(), "chrome-usa")
    os.makedirs(d, exist_ok=True)
    return d


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


def gh_bin():
    d = os.path.join(app_dir(), "bin")
    os.makedirs(d, exist_ok=True)
    if os.name == "nt":
        return os.path.join(d, "gh.exe")
    return os.path.join(d, "gh")


def ensure_gh(log=print):
    """Download GitHub CLI once. Returns path to gh binary."""
    exe = gh_bin()
    if os.path.exists(exe):
        return exe
    log("Downloading GitHub login helper (one time) ...")
    if os.name == "nt":
        asset = f"gh_{GH_VERSION}_windows_amd64.zip"
    else:
        asset = f"gh_{GH_VERSION}_linux_amd64.tar.gz"
    url = f"https://github.com/cli/cli/releases/download/v{GH_VERSION}/{asset}"
    tmp = os.path.join(os.path.dirname(exe), asset)
    urllib.request.urlretrieve(url, tmp)
    if tmp.endswith(".zip"):
        with zipfile.ZipFile(tmp, "r") as z:
            z.extractall(os.path.dirname(exe))
        for root, _, files in os.walk(os.path.dirname(exe)):
            if "gh.exe" in files:
                shutil.copy(os.path.join(root, "gh.exe"), exe)
                break
    else:
        import tarfile
        with tarfile.open(tmp, "r:gz") as t:
            t.extractall(os.path.dirname(exe))
        for root, _, files in os.walk(os.path.dirname(exe)):
            if "gh" in files and not root.endswith(".git"):
                shutil.copy(os.path.join(root, "gh"), exe)
                break
    try:
        os.remove(tmp)
    except Exception:
        pass
    if os.name != "nt":
        os.chmod(exe, 0o755)
    return exe


def gh_run(*args, timeout=30):
    try:
        p = subprocess.run([gh_bin()] + list(args), capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 99, str(e)


def gh_logged_in():
    code, _ = gh_run("auth", "status")
    return code == 0


def gh_login_flow():
    """Browser login: user only clicks in GitHub, no token to copy."""
    print("Opening GitHub login in your browser ...", flush=True)
    print("Click Authorize, then return here.", flush=True)
    rc = subprocess.call([gh_bin(), "auth", "login", "--web",
                          "--skip-ssh-key"])
    if rc != 0 or not gh_logged_in():
        raise RuntimeError("GitHub login did not complete. Try again.")
    print("GitHub login OK.", flush=True)


def gh_token():
    code, out = gh_run("auth", "token")
    if code == 0 and out:
        return out.splitlines()[0].strip()
    return ""


def gh_username(token):
    code, data = api_req("GET", f"{API}/user", token)
    if code == 200 and data.get("login"):
        return data["login"]
    return ""


def api_token(cfg):
    """Auth for API calls: saved token, else live gh login token."""
    if cfg.get("token"):
        return cfg["token"]
    return gh_token()


def api_req(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "ignore")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            detail = ""
        return e.code, {"error": detail}
    except Exception as e:
        return 0, {"error": str(e)[:300]}


def raw_get(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def parse_repo_url(s):
    s = (s or "").strip().strip('"').strip("'")
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", s)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"([^/\s]+)/([^/\s]+?)(?:\.git)?$", s)
    if m and "/" in s and " " not in s:
        return m.group(1), m.group(2)
    return None


def download_template(path):
    return raw_get(f"{RAW}/{CANONICAL_REPO}/main/{path}")


def put_file(owner, repo, token, path, content, msg):
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    sha = None
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            sha = json.loads(r.read().decode()).get("sha")
    except Exception:
        sha = None
    payload = {"message": msg,
               "content": base64.b64encode(content.encode("utf-8")).decode()}
    if sha:
        payload["sha"] = sha
    return api_req("PUT", url, token, payload)


def setup_backend(repo_name, log):
    """Browser login -> create/reuse repo -> upload -> start -> wait. Returns cfg."""
    ensure_gh(log)
    if not gh_logged_in():
        log("A browser window will open: click Authorize on GitHub.")
        gh_login_flow()
    token = gh_token()
    if not token:
        raise RuntimeError("Could not get GitHub access. Try again.")
    owner = gh_username(token)
    if not owner:
        raise RuntimeError("Could not read GitHub username. Try again.")
    parsed = parse_repo_url(repo_name or "")
    if parsed:
        # user pasted a repo URL: use its repo name (must belong to them)
        repo = parsed[1]
    else:
        repo = re.sub(r"[^A-Za-z0-9_.-]", "-", (repo_name or "my-usa-proxy").strip()) or "my-usa-proxy"
    log(f"Checking {owner}/{repo} ...")
    code, _ = api_req("GET", f"{API}/repos/{owner}/{repo}", token)
    if code == 404:
        log(f"Creating public repo {repo} ...")
        code, _ = api_req("POST", f"{API}/user/repos", token,
                          {"name": repo, "private": False,
                           "description": "My private USA proxy (IPNET)"})
        if code not in (200, 201):
            raise RuntimeError("Could not create the repo. Create it manually at "
                               "https://github.com/new (Public, empty).")
    elif code != 200:
        raise RuntimeError("Cannot access the repo. Make it PUBLIC.")
    password = "X5_" + secrets.token_urlsafe(14).replace("-", "S").replace("_", "s") + "!Strong"
    for src in PROJECT_FILES:
        # USER_README.md becomes the repo's README.md (no secrets inside)
        path = "README.md" if src == "USER_README.md" else src
        log(f"Uploading {path} ...")
        content = download_template(src)
        if not content:
            raise RuntimeError(f"Cannot download template {src}. Check internet.")
        content = content.replace("X5_Secure_2026!Strong", password)
        code, _ = put_file(owner, repo, token, path, content, f"x5proxy: add {path}")
        if code not in (200, 201):
            raise RuntimeError(f"Upload of {path} failed (HTTP {code}).")
        time.sleep(0.5)
    log("Starting your USA server ...")
    code, _ = api_req("POST",
                      f"{API}/repos/{owner}/{repo}/actions/workflows/proxy.yml/dispatches",
                      token, {"ref": "main"})
    if code not in (201, 204):
        log("Auto-start got HTTP %s. You can start it once manually:" % code)
        log(f"https://github.com/{owner}/{repo}/actions")
    log("Waiting for the encrypted endpoint (up to ~12 min) ...")
    endpoint = ""
    started = time.time()
    for i in range(48):
        time.sleep(15)
        v = raw_get(f"{RAW}/{owner}/{repo}/main/ss_url.txt")
        if re.match(r"bore\.pub:\d+", v or ""):
            endpoint = v
            break
        mins = int((time.time() - started) // 60) + 1
        log(f"... still building (~{mins} min elapsed)")
    cfg = {"owner": owner, "repo": repo,
           "password": password, "method": SS_METHOD}
    save_config(cfg)
    if endpoint:
        log(f"Ready! Endpoint: {endpoint}")
    else:
        log("Server still building - the app will pick it up automatically.")
    return cfg


def gui_setup(error_msg=""):
    """IPNET setup window. Editorial minimalism: warm white, off-black type,
    hairline dividers, one solid CTA. Returns cfg or None if closed."""
    import tkinter as tk
    from tkinter import filedialog
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

    def field(text, mono=False):
        e = tk.Entry(wrap, bg=FIELD, fg=INK, relief="solid", borderwidth=1,
                     highlightthickness=1, highlightcolor=INK,
                     highlightbackground=HAIR,
                     font=("Consolas", 9) if mono else ("Segoe UI", 10),
                     insertbackground=INK)
        e.insert(0, text)
        e.config(state="readonly")
        e.pack(fill="x", pady=3)
        make_copyable(e)
        return e

    def make_copyable(widget):
        """Guaranteed copy: Ctrl+C / Ctrl+Insert / right-click menu + toast."""
        def do_copy(_evt=None):
            try:
                sel = widget.selection_get()
            except Exception:
                try:
                    sel = widget.get()
                except Exception:
                    return "break"
            copy_text(sel, "Copied!")
            return "break"

        widget.bind("<Control-c>", do_copy)
        widget.bind("<Control-C>", do_copy)
        widget.bind("<Control-Insert>", do_copy)
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Copy",
                         command=lambda: (do_copy(), menu.unpost()))

        def popup(evt):
            try:
                widget.focus_set()
                menu.tk_popup(evt.x_root, evt.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", popup)

    tk.Label(wrap, text="USA proxy in one click.", bg=PAPER, fg=MUTED,
             font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 14))

    tk.Label(wrap, text="1  —  GitHub account", bg=PAPER, fg=INK,
             font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Free, once.  Click the link to copy it.",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
    # clickable link card: single click copies + toast (realistic for tk)
    LINK_BG, LINK_FG = "#EFF6FF", "#1D4ED8"
    link_card = tk.Frame(wrap, bg=LINK_BG, highlightthickness=1,
                         highlightbackground="#BFDBFE")
    link_card.pack(fill="x", pady=3)
    link_lbl = tk.Label(link_card, text="https://github.com/signup",
                        bg=LINK_BG, fg=LINK_FG, cursor="hand2",
                        font=("Consolas", 9, "underline"))
    link_lbl.pack(side="left", padx=10, pady=8)
    hint_lbl = tk.Label(link_card, text="Click to copy",
                        bg=LINK_BG, fg="#60A5FA", font=("Segoe UI", 8))
    hint_lbl.pack(side="right", padx=10)

    def _copy_signup(_evt=None):
        copy_text("https://github.com/signup", "Link copied!")

    for _w in (link_card, link_lbl, hint_lbl):
        _w.bind("<Button-1>", _copy_signup)
        _w.configure(cursor="hand2")
    hairline()

    tk.Label(wrap, text="2  —  Repo name or URL", bg=PAPER, fg=INK,
             font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Example: my-usa-proxy  or  https://github.com/YOU/my-usa-proxy",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
    repo_var = tk.StringVar(value="")
    tk.Entry(wrap, textvariable=repo_var, bg=FIELD, fg=INK, relief="solid",
             borderwidth=1, highlightthickness=1, highlightcolor=INK,
             highlightbackground=HAIR, font=("Segoe UI", 9),
             insertbackground=INK).pack(fill="x", pady=3)
    hairline()

    tk.Label(wrap, text="3  —  Storage folder", bg=PAPER, fg=INK,
             font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(wrap, text="Leave it, or Browse to choose another folder.",
             bg=PAPER, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
    row = tk.Frame(wrap, bg=PAPER)
    row.pack(fill="x", pady=3)
    path_var = tk.StringVar(value=get_data_dir())
    tk.Entry(row, textvariable=path_var, bg=FIELD, fg=INK, relief="solid",
             borderwidth=1, highlightthickness=1, highlightcolor=INK,
             highlightbackground=HAIR, font=("Consolas", 8),
             insertbackground=INK).pack(side="left", fill="x", expand=True,
                                        padx=(0, 8))

    def on_browse():
        d = filedialog.askdirectory(title="IPNET storage folder",
                                    initialdir=path_var.get() or get_data_dir())
        if d:
            path_var.set(d)

    browse_btn = RoundedButton(row, text="Browse", command=on_browse,
                               width=110, height=34, radius=10,
                               bg=PAPER, fg=INK,
                               normal="#FFFFFF", hover="#F3F4F6",
                               pressed="#E5E7EB", disabled="#F3F4F6",
                               font=("Segoe UI", 9, "bold"),
                               border=1, border_color="#E0E0E0")
    browse_btn.pack(side="right")
    hairline()

    tk.Label(wrap, text="Press Start, click Authorize in the browser. The rest is automatic.",
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
        name = (repo_var.get() or "").strip()
        if not name:
            status.set("Type a repo name (my-usa-proxy) or paste a repo URL.")
            return
        d = (path_var.get() or "").strip() or get_data_dir()
        enabled["v"] = False
        btn.set_enabled(False)
        try:
            set_data_dir(d)
        except Exception as e:
            status.set(f"Cannot use that folder: {e}")
            enabled["v"] = True
            btn.set_enabled(True)
            return
        status.set("Working ... browser login, then full auto setup. Check the terminal window too.")
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
            cfg = setup_backend(name, log)
            result["cfg"] = cfg
            status.set("Ready! Restarting into run mode ...")
            pb.stop()
            root.update()
            time.sleep(1)
            root.destroy()
        except Exception as e:
            pb.stop()
            pb.pack_forget()
            status.set(f"Error: {e}")
            enabled["v"] = True
            btn.set_enabled(True)

    tk.Frame(wrap, bg=HAIR, height=1).pack(fill="x", pady=(10, 8))
    tk.Label(wrap, text=f"{APP_NAME} {APP_VERSION}", bg=PAPER, fg=MUTED,
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
    print(f"Downloading sing-box {SB_VERSION} (one time)...", flush=True)
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


def endpoint_reachable(endpoint, timeout=10):
    import socket
    try:
        host, _, port = endpoint.partition(":")
        s = socket.create_connection((host.strip(), int(port)), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


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


def cancel_stuck_runs(cfg):
    """Cancel any in-progress proxy runs so a fresh one can take over."""
    token = api_token(cfg)
    if not token:
        return 0
    try:
        code, data = api_req(
            "GET",
            f"{API}/repos/{cfg['owner']}/{cfg['repo']}"
            "/actions/workflows/proxy.yml/runs?status=in_progress&per_page=5",
            token)
        if code != 200:
            return 0
        n = 0
        for r in (data.get("workflow_runs") or []):
            rc, _ = api_req("POST",
                            f"{API}/repos/{cfg['owner']}/{cfg['repo']}"
                            f"/actions/runs/{r['id']}/cancel",
                            token)
            if rc in (202, 204):
                n += 1
        return n
    except Exception:
        return 0


def request_fresh_server(cfg, log=print):
    """Ask GitHub for a brand-new server run. Returns True if accepted."""
    token = api_token(cfg)
    if not token:
        log("GitHub session expired. Restart the app to log in again.")
        return False
    cancel_stuck_runs(cfg)
    code, data = api_req(
        "POST",
        f"{API}/repos/{cfg['owner']}/{cfg['repo']}/actions/workflows/proxy.yml/dispatches",
        token, {"ref": "main"})
    if code in (201, 204):
        log("Fresh server requested. Waiting for the new endpoint ...")
        return True
    log(f"Could not request a fresh server (HTTP {code}). Will retry later.")
    return False


def tunnel_log_path():
    return os.path.join(app_dir(), "singbox.log")


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


def open_usa_chrome(chrome, url=None):
    """Open Chrome with a USA identity: English UI+content, no WebRTC leak.
    url is opened only when given (first run); otherwise a normal window."""
    profile = os.path.join(app_dir(), "chrome-usa")
    os.makedirs(profile, exist_ok=True)
    # seed Accept-Language once (Chrome stores it in Preferences)
    prefs = os.path.join(profile, "Preferences")
    try:
        if not os.path.exists(prefs):
            with open(prefs, "w", encoding="utf-8") as f:
                json.dump({"intl": {"accept_languages": "en-US,en"}}, f)
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
        print("Chrome opened (USA profile: English, WebRTC leak blocked).",
              flush=True)
    except Exception as e:
        print(f"Could not open Chrome: {e}", flush=True)


def run_terminal(cfg):
    """Terminal loop: show proxy address, refresh endpoint, open Chrome.
    Raises RuntimeError if the repo/endpoint is unusable -> GUI reopens."""
    free_local_port()
    exe = ensure_singbox()
    chrome = find_chrome()
    if not chrome:
        print("WARNING: Chrome not found. Install Google Chrome first.")
    # keep the tunnel log from growing forever (old ERROR floods)
    try:
        _lp = tunnel_log_path()
        if os.path.exists(_lp) and os.path.getsize(_lp) > 2 * 1024 * 1024:
            open(_lp, "w").close()
            print("Old tunnel log cleared (>2MB).", flush=True)
    except Exception:
        pass
    # repo sanity check (needs GitHub session only for healing/dispatch)
    token = api_token(cfg)
    if token:
        code, _ = api_req("GET", f"{API}/repos/{cfg['owner']}/{cfg['repo']}",
                          token)
        if code == 404:
            raise RuntimeError("Repo not found (renamed/deleted?). Enter it again.")
        if code == 401:
            print("GitHub session expired - you will be asked to log in again if needed.",
                  flush=True)
    proc = None
    tun_log = None
    current = ""
    dead = 0
    last_heal = 0
    client_cfg = os.path.join(app_dir(), "sb-client.json")
    print("=" * 60)
    print(f"  {APP_NAME} {APP_VERSION} - USA proxy (leave this window OPEN)")
    print("=" * 60)
    print(f"Repo: {cfg['owner']}/{cfg['repo']}")
    print("Press Ctrl+C to stop.\n", flush=True)
    fails = 0
    try:
        while True:
            name, endpoint = fetch_endpoint(cfg)
            if not endpoint:
                fails += 1
                print(f"Endpoint not published yet ({fails}). "
                      f"Check https://github.com/{cfg['owner']}/{cfg['repo']}/actions",
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
                print("-" * 60)
                print(f"PROXY ADDRESS (manual use): 127.0.0.1:{LOCAL_SOCKS_PORT} (SOCKS5 + HTTP)")
                print(f"SERVER: {endpoint} "
                      f"({'encrypted' if name == 'ss_url.txt' else 'plain http'})")
                print("IP: USA (Phoenix, Arizona)")
                print("-" * 60, flush=True)
                if chrome:
                    if not cfg.get("welcomed"):
                        open_usa_chrome(chrome, "https://ipleak.net/")
                        cfg["welcomed"] = True
                        save_config(cfg)
                    else:
                        open_usa_chrome(chrome)
            if proc and proc.poll() not in (None, 0):
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                print("Local tunnel restarted.", flush=True)
            # --- client-side healing: does traffic REALLY flow? ---
            # (TCP to bore.pub is not enough: the tunnel can be up while
            # the server-side proxy refuses everything -> ERROR flood.)
            if current and proxy_working():
                if dead:
                    print("Proxy is working again.", flush=True)
                dead = 0
            elif current:
                dead += 1
                print(f"Proxy not responding ({dead}/3) - getting a new one ...",
                      flush=True)
                if dead >= 3 and time.time() - last_heal > 900:
                    last_heal = time.time()
                    dead = 0
                    print("Requesting a fresh USA server (takes a few minutes) ...",
                          flush=True)
                    if request_fresh_server(cfg):
                        # wait until a DIFFERENT endpoint is published
                        for _w in range(48):
                            time.sleep(15)
                            _, fresh = fetch_endpoint(cfg)
                            if fresh and fresh != current:
                                print(f"New endpoint: {fresh}", flush=True)
                                break
                            if (_w + 1) % 4 == 0:
                                print(f"... waiting for new server "
                                      f"({(_w + 1) * 15 // 60} min so far)",
                                      flush=True)
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_tunnel(proc, tun_log)


def restart_fresh():
    """Relaunch a clean copy of this app, then exit (used after setup)."""
    try:
        args = [a for a in sys.argv[1:] if a != "--reset"]
        subprocess.Popen([sys.executable] + args)
    except Exception as e:
        print(f"Auto-restart failed ({e}). Please open the app again.",
              flush=True)
        return False
    return True


def main():
    if "--reset" in sys.argv:
        try:
            os.remove(config_path())
        except Exception:
            pass
    try:
        while True:
            cfg = load_config()
            if not cfg:
                cfg = gui_setup()
                if not cfg:
                    return  # user closed the window
                print("Setup complete. Restarting into run mode ...", flush=True)
                time.sleep(1)
                if restart_fresh():
                    return
                # fall through to run_terminal if relaunch failed
            try:
                run_terminal(cfg)
                return
            except RuntimeError as e:
                print(f"Problem: {e}", flush=True)
                try:
                    os.remove(config_path())
                except Exception:
                    pass
                cfg = gui_setup(str(e))
                if not cfg:
                    return
                print("Setup complete. Restarting into run mode ...", flush=True)
                time.sleep(1)
                if restart_fresh():
                    return
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nUnexpected error: {e}", flush=True)
        try:
            input("Press Enter to close ...")
        except Exception:
            pass


if __name__ == "__main__":
    main()
