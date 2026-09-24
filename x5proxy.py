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

Windows: config at %APPDATA%/X5Proxy/config.json
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
APP_VERSION = "v1"
CANONICAL_REPO = "X5Coder/proxy-usa"  # templates are downloaded from here
PROJECT_FILES = [
    "server.py",
    "singbox-server.json",
    ".github/workflows/proxy.yml",
    "ss-client-template.json",
    ".gitignore",
]
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
SB_VERSION = "1.14.2"
GH_VERSION = "2.101.0"
SS_METHOD = "aes-256-gcm"
LOCAL_SOCKS_PORT = 1080


def app_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "X5Proxy")
    else:
        d = os.path.join(os.path.expanduser("~"), ".x5proxy")
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
    for path in PROJECT_FILES:
        log(f"Uploading {path} ...")
        content = download_template(path)
        if not content:
            raise RuntimeError(f"Cannot download template {path}. Check internet.")
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
    for i in range(48):
        time.sleep(15)
        v = raw_get(f"{RAW}/{owner}/{repo}/main/ss_url.txt")
        if re.match(r"bore\.pub:\d+", v or ""):
            endpoint = v
            break
        log(f"... still building ({i + 1}/48)")
    cfg = {"owner": owner, "repo": repo,
           "password": password, "method": SS_METHOD}
    save_config(cfg)
    if endpoint:
        log(f"Ready! Endpoint: {endpoint}")
    else:
        log("Server still building - the app will pick it up automatically.")
    return cfg


def gui_setup(error_msg=""):
    """IPNET setup window: custom design, copyable text. Returns cfg or None."""
    import tkinter as tk
    result = {}

    BG, CARD, ACCENT, TEXT, MUTED = "#0f172a", "#1e293b", "#38bdf8", "#e2e8f0", "#94a3b8"

    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION} - Setup (one time)")
    root.geometry("560x640")
    root.resizable(False, False)
    root.configure(bg=BG)
    for p in (resource_path("ipnet.ico"), resource_path("ipnet.png")):
        if p:
            try:
                if p.endswith(".ico"):
                    root.iconbitmap(p)
                else:
                    _img = tk.PhotoImage(file=p)
                    root.iconphoto(True, _img)
                    root._icon_ref = _img
                break
            except Exception:
                continue

    def label(parent, text, size=10, bold=False, fg=TEXT, anchor="w"):
        w = tk.Label(parent, text=text, bg=BG, fg=fg, anchor=anchor,
                     justify="left", font=("Segoe UI", size, "bold" if bold else "normal"))
        w.pack(anchor="w", fill="x")
        return w

    def copyable(parent, text):
        """Selectable + copyable line (Ctrl+C works)."""
        e = tk.Entry(parent, bg=CARD, fg=ACCENT, relief="flat",
                     font=("Consolas", 8), insertbackground=ACCENT)
        e.insert(0, text)
        e.config(state="readonly")
        e.pack(fill="x", pady=1)
        return e

    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=18, pady=(14, 0))
    try:
        _logo = tk.PhotoImage(file=resource_path("ipnet.png")).subsample(4, 4)
        tk.Label(head, image=_logo, bg=BG).pack(side="left", padx=(0, 10))
        root._logo_ref = _logo
    except Exception:
        pass
    tk.Label(head, text=f"{APP_NAME}  {APP_VERSION}", bg=BG, fg=TEXT,
             font=("Segoe UI", 16, "bold")).pack(side="left")
    label(head, "USA proxy in one click", size=9, fg=MUTED)

    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=18, pady=10)

    label(body, "1. Create a free GitHub account (once):", bold=True)
    copyable(body, "https://github.com/signup")
    label(body, "2. Type a repo name OR paste a repo URL below.", bold=True)
    repo_var = tk.StringVar(value="my-usa-proxy")
    tk.Entry(body, textvariable=repo_var, bg=CARD, fg=TEXT, relief="flat",
             font=("Segoe UI", 10), insertbackground=ACCENT).pack(fill="x", pady=(2, 6))
    label(body, "3. Press Start, click Authorize in the browser.", bold=True)
    label(body, "The app then creates the repo, uploads everything and starts the USA server — fully automatic.", size=9, fg=MUTED)

    label(body, "Storage on this PC (select + Ctrl+C to copy):", size=9, bold=True, fg=MUTED)
    copyable(body, f"Settings:  {config_path()}")
    copyable(body, f"Chrome USA profile:  {profile_dir()}")
    copyable(body, f"Helpers (gh, sing-box):  {bin_dir()}")

    status = tk.StringVar(value=error_msg)
    tk.Label(body, textvariable=status, bg=BG, fg="#f87171", wraplength=520,
             justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

    def on_start():
        name = (repo_var.get() or "").strip()
        if not name:
            status.set("Type a repo name (my-usa-proxy) or paste a repo URL.")
            return
        btn.config(state="disabled")
        status.set("Working ... browser login, then full auto setup.\nCheck the black terminal window too.")
        root.update()
        try:
            cfg = setup_backend(name, status.set)
            result["cfg"] = cfg
            root.destroy()
        except Exception as e:
            status.set(f"Error: {e}")
            btn.config(state="normal")

    btn = tk.Button(body, text="Start", command=on_start, bg=ACCENT, fg="#0f172a",
                    activebackground="#7dd3fc", relief="flat",
                    font=("Segoe UI", 11, "bold"), padx=30, pady=6)
    btn.pack(pady=10)
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


def open_usa_chrome(chrome):
    """Open Chrome with a USA identity: English UI+content, no WebRTC leak."""
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
        subprocess.Popen([
            chrome, f"--user-data-dir={profile}",
            f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
            "--lang=en-US",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "https://ipinfo.io/"])
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
                    "log": {"level": "warn"},
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
                    open_usa_chrome(chrome)
            if proc and proc.poll() not in (None, 0):
                stop_tunnel(proc, tun_log)
                proc, tun_log = start_tunnel(exe, client_cfg)
                print("Local tunnel restarted.", flush=True)
            # --- client-side healing: is the tunnel actually reachable? ---
            if current and endpoint_reachable(current):
                if dead:
                    print("Tunnel is reachable again.", flush=True)
                dead = 0
            elif current:
                dead += 1
                print(f"Server tunnel expired ({dead}/3) - getting a new one ...",
                      flush=True)
                if dead >= 3 and time.time() - last_heal > 900:
                    last_heal = time.time()
                    dead = 0
                    print("Requesting a fresh USA server (takes a few minutes) ...",
                          flush=True)
                    if request_fresh_server(cfg):
                        # wait until a DIFFERENT endpoint is published
                        for _ in range(48):
                            time.sleep(15)
                            _, fresh = fetch_endpoint(cfg)
                            if fresh and fresh != current:
                                print(f"New endpoint: {fresh}", flush=True)
                                break
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_tunnel(proc, tun_log)


def main():
    if "--reset" in sys.argv:
        try:
            os.remove(config_path())
        except Exception:
            pass
    while True:
        cfg = load_config()
        if not cfg:
            cfg = gui_setup()
            if not cfg:
                return  # user closed the window
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


if __name__ == "__main__":
    main()
