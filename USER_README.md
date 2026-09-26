# My USA Proxy

Private USA proxy server, deployed automatically by **IPNET**.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

Developer: **X5Coder**

Original project: https://github.com/X5Coder/proxy-usa

## What is this?

Free USA server (GitHub Actions) running an encrypted Shadowsocks proxy.
It checks itself every minute, heals on first failure, and keeps everything
below up to date automatically. The `sub.txt` link never changes — only its
content tracks the live server.

<!--IPNET-LIVE-START-->
Live info appears here automatically after the first run.
<!--IPNET-LIVE-END-->

## Windows (IPNET.exe)

1. Download **`IPNET.exe`** from https://github.com/X5Coder/proxy-usa/releases.
2. Paste **this repo's link** → **Start** → Chrome opens via USA IP.
3. Every launch: same screen (link saved) → Start.

## Android (v2rayNG) — step by step

1. Install **v2rayNG** ([direct APK `arm64-v8a`](https://github.com/2dust/v2rayNG/releases/download/2.2.6/v2rayNG_2.2.6_arm64-v8a.apk)).
2. Copy the subscription URL from the live block above.
3. Open v2rayNG → top-left menu → **Subscription group setting** → **+**.
4. Fill exactly:
   - **remarks**: any name (e.g. `IPNET`).
   - **Optional URL**: paste the subscription URL here (this is the important field).
   - Turn **Enable update** ON.
   - Turn **Enable automatic update** ON.
   - **Auto Update Interval**: `60` (minimum allowed is 15).
   - Leave everything else as is → press **✓** (top right) to save.
5. Back on the main screen → **⋮** menu → **Update subscription** → server `IPNET-USA` appears.
6. Tap the server to select it → press **▶** (bottom right) → allow VPN.
7. Open `ipinfo.io` in the browser → United States.
8. If it stops later: **⋮** → **Update subscription** → connect again (5 seconds).

## Files

- `server.py` — forward proxy (HTTP + HTTPS)
- `singbox-server.json` — encrypted Shadowsocks server
- `.github/workflows/proxy.yml` — runs everything, self-heals
- `ss_url.txt` — current encrypted endpoint (auto-updated)
- `sub.txt` — fixed subscription link for phone apps (auto-updated)
- `android-ss.txt` — plain ss:// link (copy/QR)

## Do not

Do not delete `ss_url.txt` or `sub.txt` — apps read the current address from them.
Public repos give automatic phone updates; private repos need manual copy.

---
Made with IPNET — by X5Coder — https://www.youtube.com/@Kareem-X5Coder
