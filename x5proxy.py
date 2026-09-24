#!/usr/bin/env python3
"""
X5Proxy - one-click USA proxy.
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

APP_NAME = "X5Proxy"
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


def setup_backend(owner, repo, token, log):
    """Upload project, dispatch workflow, wait for endpoint. Returns cfg."""
    log(f"Checking {owner}/{repo} ...")
    code, data = api_req("GET", f"{API}/repos/{owner}/{repo}", token)
    if code != 200:
        raise RuntimeError("Cannot access repo. Make it PUBLIC and allow "
                           "[repo]+[workflow] token scopes.")
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
    cfg = {"owner": owner, "repo": repo, "token": token,
           "password": password, "method": SS_METHOD}
    save_config(cfg)
    if endpoint:
        log(f"Ready! Endpoint: {endpoint}")
    else:
        log("Server still building - the app will pick it up automatically.")
    return cfg


def gui_setup(error_msg=""):
    """Very simple setup window. Returns cfg or None if closed."""
    import tkinter as tk
    from tkinter import ttk
    result = {}

    root = tk.Tk()
    root.title("X5Proxy - Setup (one time)")
    root.geometry("520x560")
    root.resizable(False, False)

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="X5Proxy - USA proxy in one click",
              font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(frm, text="Do these 3 steps once, then press Start:",
              font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 4))
    steps = ("1. Create a free GitHub account:\n"
             "     https://github.com/signup\n\n"
             "2. Create a NEW PUBLIC empty repository:\n"
             "     https://github.com/new  (Public, no README)\n\n"
             "3. Create a token (copy it):\n"
             "     https://github.com/settings/tokens/new\n"
             "     scopes: [repo] + [workflow]")
    ttk.Label(frm, text=steps, font=("Segoe UI", 9),
              justify="left").pack(anchor="w")

    ttk.Label(frm, text="Repo URL:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 0))
    repo_var = tk.StringVar()
    ttk.Entry(frm, textvariable=repo_var, width=60).pack(fill="x")
    ttk.Label(frm, text="Example: https://github.com/YOU/my-usa-proxy",
              font=("Segoe UI", 8)).pack(anchor="w")

    ttk.Label(frm, text="Token:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
    tok_var = tk.StringVar()
    ttk.Entry(frm, textvariable=tok_var, width=60, show="*").pack(fill="x")

    status = tk.StringVar(value=error_msg)
    ttk.Label(frm, textvariable=status, font=("Segoe UI", 9),
              foreground="red", wraplength=480).pack(anchor="w", pady=(8, 0))

    def on_start():
        parsed = parse_repo_url(repo_var.get())
        if not parsed:
            status.set("Invalid repo URL. Example: https://github.com/YOU/my-usa-proxy")
            return
        if not tok_var.get().strip():
            status.set("Token is empty. Create one at github.com/settings/tokens/new")
            return
        owner, repo = parsed
        btn.config(state="disabled")
        status.set("Working ... uploading project and starting the server.")
        root.update()
        try:
            cfg = setup_backend(owner, repo, tok_var.get().strip(), status.set)
            result["cfg"] = cfg
            root.destroy()
        except Exception as e:
            status.set(f"Error: {e}")
            btn.config(state="normal")

    btn = ttk.Button(frm, text="Start", command=on_start)
    btn.pack(pady=12)
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


def run_terminal(cfg):
    """Terminal loop: show proxy address, refresh endpoint, open Chrome.
    Raises RuntimeError if the repo/endpoint is unusable -> GUI reopens."""
    free_local_port()
    exe = ensure_singbox()
    chrome = find_chrome()
    if not chrome:
        print("WARNING: Chrome not found. Install Google Chrome first.")
    # repo sanity check
    code, _ = api_req("GET", f"{API}/repos/{cfg['owner']}/{cfg['repo']}",
                      cfg.get("token", ""))
    if code == 404:
        raise RuntimeError("Repo not found (renamed/deleted?). Enter the URL again.")
    proc = None
    current = ""
    client_cfg = os.path.join(app_dir(), "sb-client.json")
    print("=" * 60)
    print("  X5Proxy - USA proxy (leave this window OPEN)")
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
                    "log": {"level": "info"},
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
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
                proc = subprocess.Popen([exe, "run", "-c", client_cfg])
                print("-" * 60)
                print(f"PROXY ADDRESS (manual use): 127.0.0.1:{LOCAL_SOCKS_PORT} (SOCKS5 + HTTP)")
                print(f"SERVER: {endpoint} "
                      f"({'encrypted' if name == 'ss_url.txt' else 'plain http'})")
                print("IP: USA (Phoenix, Arizona)")
                print("-" * 60, flush=True)
                if chrome:
                    profile = os.path.join(app_dir(), "chrome-usa")
                    os.makedirs(profile, exist_ok=True)
                    try:
                        subprocess.Popen([chrome, f"--user-data-dir={profile}",
                                          f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
                                          "https://ipinfo.io/"])
                        print("Chrome opened through the USA proxy.", flush=True)
                    except Exception as e:
                        print(f"Could not open Chrome: {e}", flush=True)
            if proc and proc.poll() not in (None, 0):
                proc = subprocess.Popen([exe, "run", "-c", client_cfg])
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass


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
