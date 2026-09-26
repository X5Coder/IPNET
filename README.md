# IPNET — USA proxy in one click

Free USA proxy (GitHub Actions) + Windows app + phone subscription.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

Developer: **X5Coder** — Original repo: `https://github.com/X5Coder/proxy-usa`

## 1. Make your server (once, 1 click)

1. Open `https://github.com/X5Coder/proxy-usa` → **Use this template** → create your repo (public).
2. Open the **Actions** tab in your repo → run **USA Proxy** once if not already running.
3. After a few minutes open **`README.md`** in your repo — copy from there.

## 2. Windows

1. Download **`IPNET.exe`** from [Releases](../../releases), run it.
2. Paste **your repo link** → **Start** → Chrome opens via USA IP.
3. Every launch: same screen (link saved) → Start.

## 3. Android (v2rayNG) — step by step

1. Install **v2rayNG** — tap to download directly ([v2rayNG_2.2.6 `arm64-v8a`](https://github.com/2dust/v2rayNG/releases/download/2.2.6/v2rayNG_2.2.6_arm64-v8a.apk)).
2. Top-left menu → **Subscription group setting** → **+**, fill exactly:
   - **remarks**: any name, e.g. `IPNET`.
   - **Optional URL**: your subscription link, e.g.
     `https://raw.githubusercontent.com/YOU/YOUR-REPO/main/sub.txt`
     (replace `YOU/YOUR-REPO` — the exact link is in your repo's `README.md`).
   - **Enable update**: ON.
   - **Enable automatic update**: ON, interval `60`.
   - Leave the rest → press **✓** (top right) to save.
3. Back on the main screen → **⋮** menu → **Update subscription** → server `IPNET-USA` appears.
4. Tap the server to select it → press **▶** (bottom right) → allow VPN.
5. Open `ipinfo.io` → United States.
6. No internet despite connected? Settings → find **Remote DNS** → set
   `https://1.1.1.1/dns-query` → reconnect. Later disconnects? **⋮** →
   **Update subscription** → connect again (5 seconds).

## How it works

- Actions (USA) runs HTTP proxy + encrypted Shadowsocks, exposed via `bore` tunnels.
- Self-checks every minute, heals on first failure, publishes the new port to `ss_url.txt` + `sub.txt` + your repo `README.md`.
- **One fixed link forever**: `sub.txt`. Ports rotate (~5h), the link never changes.
- ISPs blocking plain `CONNECT` see only encrypted traffic.

## Rights

Original: `https://github.com/X5Coder/proxy-usa` — by **X5Coder**.
Do not remove credits. Tutorials: https://www.youtube.com/@Kareem-X5Coder
