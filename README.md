# IPNET v1 — USA proxy in one click

Download **`IPNET.exe`** from [Releases](../../releases) and double-click it.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

Developer: **X5Coder**

## Setup (once, ~5 min, no tokens)

1. Create a free GitHub account.
2. Open IPNET, type a repo name, press **Start**.
3. Click **Authorize** in the browser.

Full guide: [SETUP.md](SETUP.md). The app creates the repo, uploads the
server, starts it, then opens Chrome through the USA IP by itself.

## Daily use

Double-click IPNET, leave the terminal open. It shows the proxy address
(`127.0.0.1:1080`), refreshes endpoints and heals itself automatically.

## How it works

GitHub Actions (USA) runs an HTTP proxy + encrypted Shadowsocks server,
exposed via bore tunnels. Some ISPs block plain `CONNECT`, so all traffic
goes encrypted — nothing to block.

## Files

| File | Purpose |
|---|---|
| `x5proxy.py` | Desktop app (built to `IPNET.exe`) |
| `server.py` | Forward proxy (HTTP + HTTPS) |
| `singbox-server.json` | Shadowsocks server config |
| `.github/workflows/proxy.yml` | Action: runs both, self-heals |
| `USER_README.md` | README uploaded to user repos |
| `ipnet.svg/.ico/.png` | App icon |
| `ss-client-template.json` | Manual client example |

## Notes

- SmartScreen "Unknown publisher": **More info → Run anyway** (no paid cert).
- Password is random per repo; endpoints rotate about every 5 hours.
- `ss_url.txt` is auto-published — that is how the app finds the server.
