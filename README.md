# X5Proxy — USA proxy in one click

Download **`X5Proxy.exe`** from [Releases](../../releases) and double-click it. That is all most users need.

## How it works (3 steps, one time)

1. Create a free GitHub account: https://github.com/signup
2. Create a **new PUBLIC empty repository**: https://github.com/new (Public, no README)
3. Create a token: https://github.com/settings/tokens/new — scopes **[repo]** + **[workflow]** — copy it

Open `X5Proxy.exe`, paste the **repo URL** + **token**, press **Start**. The app then automatically:

- uploads the server project to your repo (with a fresh random password),
- starts the GitHub Action (free USA server),
- waits for the encrypted endpoint,
- starts the local tunnel and opens **Chrome through the USA IP**.

## Every day use

- Double-click `X5Proxy.exe`.
- A terminal window shows the proxy address, for example:
  ```
  PROXY ADDRESS (manual use): 127.0.0.1:1080 (SOCKS5 + HTTP)
  SERVER: bore.pub:4521 (encrypted)
  IP: USA (Phoenix, Arizona)
  ```
- Chrome opens automatically through the USA IP. Leave the terminal open.
- The app refreshes the endpoint by itself (the address changes about every 5 hours).
- Manual use: point any app to `127.0.0.1:1080` as SOCKS5 (or HTTP) proxy.
- If the repo is deleted/renamed or anything breaks, the setup window opens again and asks for the repo URL.

## Why encrypted?

Some ISPs block plain proxy `CONNECT` requests, so HTTPS fails while HTTP works.
X5Proxy uses **Shadowsocks (aes-256-gcm)** — all traffic is encrypted, nothing to block.

## Files

| File | Purpose |
|---|---|
| `x5proxy.py` | The desktop app (built to `X5Proxy.exe`) |
| `server.py` | USA forward proxy (HTTP + HTTPS/CONNECT) |
| `singbox-server.json` | Encrypted Shadowsocks server config |
| `.github/workflows/proxy.yml` | GitHub Action: runs both, exposes via bore, self-heals |
| `ss-client-template.json` | Manual client example |

## Notes

- The Action runs up to 5 hours, then restarts by schedule. The app follows new endpoints automatically.
- Your password is generated per repo and stored only in your repo + your PC (`%APPDATA%/X5Proxy/config.json`).
- `bore_url.txt` / `ss_url.txt` / `proxy_urls.txt` are auto-published by the Action — that is how the app finds the current endpoint.
