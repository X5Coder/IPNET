# IPNET — USA proxy in one click

Free USA proxy (GitHub Actions) + Windows app + phone subscription.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

Developer: **X5Coder** — Original repo: `https://github.com/X5Coder/proxy-usa`

## 1. Make your server (once, 1 click)

1. Open `https://github.com/X5Coder/proxy-usa` → **Use this template** → create your repo (public).
2. Open the **Actions** tab in your repo → run **USA Proxy** once if not already running.
3. After a few minutes open **`CONNECT.md`** in your repo — copy from there.

## 2. Windows

1. Download **`IPNET.exe`** from [Releases](../../releases), run it.
2. Paste **your repo link** → **Start** → Chrome opens via USA IP.
3. Every launch: same screen (link saved) → Start.

## 3. Android (v2rayNG)

1. Install **v2rayNG** (`arm64-v8a` build).
2. Menu → Subscription settings → + → paste the `sub.txt` URL from `CONNECT.md`.
3. Update subscription → select **IPNET-USA** → connect (allow VPN).
4. Check `ipinfo.io` → United States.

## How it works

- Actions (USA) runs HTTP proxy + encrypted Shadowsocks, exposed via `bore` tunnels.
- Self-checks every minute, heals on first failure, publishes the new port to `ss_url.txt` + `sub.txt` + `CONNECT.md`.
- **One fixed link forever**: `sub.txt`. Ports rotate (~5h), the link never changes.
- ISPs blocking plain `CONNECT` see only encrypted traffic.

## Files

| File | Purpose |
|---|---|
| `x5proxy.py` | Windows app (→ `IPNET.exe`), read-only |
| `server.py` | HTTP/HTTPS forward proxy |
| `singbox-server.json` | Shadowsocks server config |
| `.github/workflows/proxy.yml` | Run + heal + publish |
| `USER_README.md` | README for new copies |

## Notes

- SmartScreen "Unknown publisher": **More info → Run anyway** (no paid cert).
- Random password per repo. Public repos only.
- Never delete `ss_url.txt`.

## Rights

Original: `https://github.com/X5Coder/proxy-usa` — by **X5Coder**.
Do not remove credits. Tutorials: https://www.youtube.com/@Kareem-X5Coder
