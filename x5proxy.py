#!/usr/bin/env python3
"""
X5Proxy - one-click USA proxy (terminal only).
First run: guides you (in English) to create a GitHub account + public repo,
then auto-uploads the server project, triggers it, waits for the encrypted
endpoint, saves everything locally, and opens Chrome through the USA IP.
Every next run: terminal shows the proxy address, starts the local tunnel,
opens Chrome. No GUI, no manual steps.

Config: %APPDATA%/X5Proxy/config.json (Windows) or ~/.x5proxy/config.json
Requires on PC: internet + Chrome. No git needed (uses GitHub API).
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
            return json.load(f)
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
    # get current sha if file exists
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
    payload = {
        "message": msg,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
    }
    if sha:
        payload["sha"] = sha
    return api_req("PUT", url, token, payload)


def first_setup():
    print("=" * 60)
    print("  X5Proxy - First time setup (takes ~5 minutes, one time only)")
    print("=" * 60)
    print()
    print("STEP 1: Create a free GitHub account (if you don't have one):")
    print("  https://github.com/signup")
    print()
    print("STEP 2: Create a NEW PUBLIC repository (empty, no README):")
    print("  https://github.com/new  -> name it e.g. 'my-usa-proxy' -> Public -> Create")
    print()
    print("STEP 3: Create a token (to let this app upload for you):")
    print("  https://github.com/settings/tokens/new")
    print("  Note: 'x5proxy-upload' | Expiration: 90 days")
    print("  Scopes: check [repo] and [workflow] -> Generate -> COPY the token")
    print("  (it looks like github_pat_... - you will paste it below)")
    print()
    while True:
        repo_in = input("Paste your NEW repo URL (e.g. https://github.com/YOU/my-usa-proxy): ").strip()
        parsed = parse_repo_url(repo_in)
        if parsed:
            owner, repo = parsed
            break
        print("  Invalid URL. Example: https://github.com/YOU/my-usa-proxy")
    import getpass
    token = getpass.getpass("Paste your GitHub token (input is hidden): ").strip()
    if not token:
        print("ERROR: token is empty. Run the app again."); sys.exit(1)

    # verify repo access
    print("Checking access to your repo...", flush=True)
    code, data = api_req("GET", f"{API}/repos/{owner}/{repo}", token)
    if code != 200:
        print(f"ERROR: cannot access {owner}/{repo} (HTTP {code}).")
        print("Make sure the repo exists, is PUBLIC, and the token has [repo]+[workflow] scopes.")
        sys.exit(1)
    print(f"OK: {owner}/{repo} reachable.")

    password = "X5_" + secrets.token_urlsafe(14).replace("-", "S").replace("_", "s") + "!Strong"
    print("Uploading proxy project to your repo...", flush=True)
    for path in PROJECT_FILES:
        content = download_template(path)
        if not content:
            print(f"ERROR: cannot download template {path}. Check internet."); sys.exit(1)
        content = content.replace("X5_Secure_2026!Strong", password)
        code, _ = put_file(owner, repo, token, path, content, f"x5proxy: add {path}")
        if code not in (200, 201):
            print(f"ERROR uploading {path} (HTTP {code})."); sys.exit(1)
        print(f"  uploaded {path}")
        time.sleep(0.5)

    print("Starting your USA server (GitHub Actions)...", flush=True)
    code, data = api_req(
        "POST",
        f"{API}/repos/{owner}/{repo}/actions/workflows/proxy.yml/dispatches",
        token, {"ref": "main"},
    )
    if code not in (201, 204):
        print(f"WARNING: workflow dispatch returned HTTP {code}: {data}.")
        print("Open your repo -> Actions -> run 'USA Proxy' manually once.")
    else:
        print("Workflow started.")

    print("Waiting for your encrypted endpoint (up to ~12 min)...", flush=True)
    ss_url = ""
    for i in range(48):
        time.sleep(15)
        ss_url = raw_get(f"{RAW}/{owner}/{repo}/main/ss_url.txt")
        if re.match(r"bore\.pub:\d+", ss_url or ""):
            break
        print(f"  ...still building ({i+1}/48)", flush=True)
        ss_url = ""
    if not ss_url:
        print("TIMEOUT: server is still building. Run the app again in a few minutes.")
        print("You can watch progress at: https://github.com/"
              f"{owner}/{repo}/actions")
    cfg = {"owner": owner, "repo": repo, "token": token,
           "password": password, "method": SS_METHOD}
    save_config(cfg)
    print("Setup saved. You will never need to do this again.", flush=True)
    return cfg


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
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as e:
        print(f"ERROR downloading sing-box: {e}"); sys.exit(1)
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
    candidates = []
    if os.name == "nt":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        for c in ("google-chrome", "chromium", "chromium-browser"):
            p = shutil.which(c)
            if p:
                return p
        return None
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return shutil.which("chrome")


def fetch_endpoint(cfg):
    for name in ("ss_url.txt", "bore_url.txt"):
        v = raw_get(f"{RAW}/{cfg['owner']}/{cfg['repo']}/main/{name}")
        if v:
            return name, v
    return "", ""


def main():
    print("=" * 60)
    print("  X5Proxy - USA proxy (terminal)")
    print("=" * 60)
    cfg = load_config()
    if not cfg and "--reset" in sys.argv:
        print("No saved setup found.")
    if not cfg:
        cfg = first_setup()
    else:
        print(f"Repo: {cfg['owner']}/{cfg['repo']}")

    exe = ensure_singbox()
    chrome = find_chrome()
    if not chrome:
        print("WARNING: Chrome not found. Install Chrome, then run again.")

    proc = None
    current = ""
    client_cfg = os.path.join(app_dir(), "sb-client.json")
    print()
    print("Starting local tunnel + Chrome. Leave this window OPEN.")
    print("Press Ctrl+C to stop.")
    print()
    try:
        while True:
            name, endpoint = fetch_endpoint(cfg)
            if endpoint and endpoint != current:
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
                print(f"PROXY ADDRESS (for manual use): 127.0.0.1:{LOCAL_SOCKS_PORT}  (SOCKS5 + HTTP)")
                print(f"SERVER: {endpoint}  ({'encrypted Shadowsocks' if name=='ss_url.txt' else 'plain HTTP'})")
                print(f"IP: USA (Phoenix, Arizona) | Method: {cfg.get('method', SS_METHOD)}")
                print("-" * 60)
                if chrome:
                    profile = os.path.join(app_dir(), "chrome-usa")
                    os.makedirs(profile, exist_ok=True)
                    try:
                        if os.name == "nt":
                            subprocess.Popen([chrome, f"--user-data-dir={profile}",
                                              f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
                                              "https://ipinfo.io/"])
                        else:
                            subprocess.Popen([chrome, f"--user-data-dir={profile}",
                                              f"--proxy-server=socks5://127.0.0.1:{LOCAL_SOCKS_PORT}",
                                              "https://ipinfo.io/"])
                        print("Chrome opened through the USA proxy.")
                    except Exception as e:
                        print(f"Could not open Chrome: {e}")
            if proc and proc.poll() not in (None, 0):
                print("Tunnel process stopped, restarting...", flush=True)
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


if __name__ == "__main__":
    main()
