<p align="center">
  <img src="ipnet.png" width="96" alt="IPNET">
</p>

<h1 align="center">IPNET</h1>

<p align="center">
  <b>USA proxy in one click.</b><br>
  Free US server (GitHub Actions) · Windows app · Phone subscription.
</p>

<p align="center">
  <a href="https://github.com/X5Coder/IPNET/releases"><img src="https://img.shields.io/github/v/release/X5Coder/IPNET?label=download&color=blue" alt="release"></a>
  <a href="https://www.youtube.com/@Kareem-X5Coder"><img src="https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=flat&logo=youtube" alt="youtube"></a>
</p>

---

## 1 · Make your server (once)

1. Open [`X5Coder/IPNET`](https://github.com/X5Coder/IPNET) → **Use this template** → create your repo (public).
2. In your repo open **Actions** → run **USA Proxy** once if not already running.
3. After a few minutes open **`README.md`** in your repo — copy from there.

## 2 · Windows

1. Download **`IPNET.exe`** from [Releases](https://github.com/X5Coder/IPNET/releases), run it.
2. Paste **your repo link** → **Start** → Chrome opens via USA IP (WebRTC + DNS leak-protected).
3. Every launch: same screen (link saved) → Start.

## 3 · Android ([v2rayNG](https://github.com/2dust/v2rayNG/releases) `arm64-v8a`)

1. Top-left menu → **Subscription group setting** → **+**, fill exactly:
   - **remarks**: `IPNET`.
   - **Optional URL**: your subscription link, e.g.
     `https://raw.githubusercontent.com/YOU/YOUR-REPO/main/sub.txt`
     (replace `YOU/YOUR-REPO` with yours).
   - **Enable update** + **Enable automatic update**: ON, interval `60`.
   - Press **✓** to save.
2. Main screen → **⋮** → **Update subscription** → tap `IPNET-USA` → **▶** → allow VPN.
3. Open [ipleak.net](https://ipleak.net/) → United States.
4. Stuck later? Restart the service from the notification, **⋮** → **Update subscription** → connect.

## How it works

- Actions (USA) runs HTTP proxy + encrypted Shadowsocks, exposed via `bore` tunnels.
- Self-checks every minute, heals on first failure, publishes the new port to `ss_url.txt` + `sub.txt` + your repo `README.md`.
- **One fixed link forever**: `sub.txt`. Ports rotate (~5h), the link never changes.
- Encrypted-only traffic (CONNECT-blocking ISPs see nothing); Chrome profile forces no-leak WebRTC policy + DNS-over-HTTPS.

---

<p align="center">
  Original: <a href="https://github.com/X5Coder/IPNET">github.com/X5Coder/IPNET</a> — by <b>X5Coder</b><br>
  Do not remove credits · Tutorials: <a href="https://www.youtube.com/@Kareem-X5Coder">YouTube</a>
</p>
