# My USA Proxy

Private USA proxy server, deployed automatically by **IPNET**.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

Developer: **X5Coder**

Original project: https://github.com/X5Coder/proxy-usa

## What is this?

Free USA server (GitHub Actions) running an encrypted Shadowsocks proxy.
The IPNET app on your PC connects to it and opens Chrome through the USA IP.

## Files

- `server.py` — forward proxy (HTTP + HTTPS)
- `singbox-server.json` — encrypted Shadowsocks server
- `.github/workflows/proxy.yml` — runs everything, self-heals
- `ss_url.txt` — current encrypted endpoint (auto-updated)
- `sub.txt` — fixed subscription link for phone apps (auto-updated)
- `CONNECT.md` — copy-paste blocks: repo link, ss link, sub link, steps

## Do not

Do not delete `ss_url.txt` — the app reads the current address from it.
Do not make this repo private — Actions minutes and raw file access work best public.

---
Made with IPNET — by X5Coder — https://www.youtube.com/@Kareem-X5Coder
