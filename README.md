# IPNET — USA proxy in one click

Download **`IPNET.exe`** from [Releases](../../releases) and double-click it. That is all most users need.

## How it works (one time, ~5 minutes, no tokens)

1. Create a free GitHub account: https://github.com/signup
2. Open `IPNET.exe`, type a name for your proxy repo, press **Start**.
3. A browser tab opens — click **Authorize** on GitHub.

The app then automatically: creates the public repo, uploads the server
project (with a fresh random password), starts the GitHub Action (free USA
server), waits for the encrypted endpoint, starts the local tunnel and opens
**Chrome through the USA IP**.

## Every day use

- Double-click `IPNET.exe`.
- A terminal window shows the proxy address, for example:
  ```
  PROXY ADDRESS (manual use): 127.0.0.1:1080 (SOCKS5 + HTTP)
  SERVER: bore.pub:4521 (encrypted)
  IP: USA (Phoenix, Arizona)
  ```
- Chrome opens automatically with a USA profile (English, WebRTC leak
  blocked) through the USA IP. Leave the terminal open.
- The app refreshes the endpoint by itself (the address changes about every
  5 hours, and the app requests a fresh server on its own if the tunnel dies).
- Manual use: point any app to `127.0.0.1:1080` as SOCKS5 (or HTTP) proxy.
- If the repo is deleted/renamed or the GitHub session expires, the setup window opens again.
- No tokens to copy: login happens in the browser via the official GitHub CLI.

## Windows SmartScreen warning

On first launch Windows may say "Unknown publisher" because the EXE is not
code-signed (a certificate costs money). It is safe: press **More info** →
**Run anyway**. The source is public in this repo and you can build the EXE
yourself with `python -m PyInstaller --onefile --console --name IPNET x5proxy.py`.

## Why encrypted?

Some ISPs block plain proxy `CONNECT` requests, so HTTPS fails while HTTP works.
IPNET uses **Shadowsocks (aes-256-gcm)** — all traffic is encrypted, nothing to block.

## Files

| File | Purpose |
|---|---|
| `x5proxy.py` | The desktop app (built to `IPNET.exe`) |
| `server.py` | USA forward proxy (HTTP + HTTPS/CONNECT) |
| `singbox-server.json` | Encrypted Shadowsocks server config |
| `.github/workflows/proxy.yml` | GitHub Action: runs both, exposes via bore, self-heals |
| `ipnet.svg` / `ipnet.ico` / `ipnet.png` | App icon (source + Windows + window) |
| `ss-client-template.json` | Manual client example |

## Notes

- The Action runs up to 5 hours, then restarts by schedule. The app follows new endpoints automatically.
- Your password is generated per repo and stored only in your repo + your PC (`%APPDATA%/X5Proxy/config.json`, shown in the setup window).
- `bore_url.txt` / `ss_url.txt` / `proxy_urls.txt` are auto-published by the Action — that is how the app finds the current endpoint.
