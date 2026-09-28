<div align="center">

<img src="ipnet.png" width="100" alt="IPNET">

# IPNET

### 🇺🇸 USA Proxy in One Click — Your Own Private USA Network

Free US server (GitHub Actions + Cloudflare tunnel) · Windows app, no admin needed · Phone subscription

> How it works: YOU deploy one file (worker.js) on YOUR OWN free Cloudflare account — no visa. GitHub only stores your worker address (one line, written once). The app and the phone subscription follow it. No GitHub Actions proxy runs, so accounts don't get banned.

<br>

<a href="README.ar.md"><img src="https://img.shields.io/badge/🇸🇦_Arabic-2ea44f?style=for-the-badge&logo=googletranslate&logoColor=white" alt="Arabic"></a>
<a href="https://www.youtube.com/@Kareem-X5Coder"><img src="https://img.shields.io/badge/YouTube-Kareem_X5Coder-ff0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube"></a>

</div>

<br>

---

## 1️⃣ Create Your Server (one-time setup, ~10 min, no visa)

> This setup is done once — after that, you're ready to connect anytime.

| Step | What to do |
|:---:|---|
| **1** | Open [`X5Coder/IPNET`](https://github.com/X5Coder/IPNET) → click **Use this template** → create your own repo (must be **Public**). |
| **2** | Deploy YOUR Worker (free, no visa, no settings): open [`dash.cloudflare.com`](https://dash.cloudflare.com/) → sign up with email → **Workers & Pages** → **Create → Start with Hello World** → **Deploy** → **Edit Code** → paste the content of **`worker.js`** from your repo → **Deploy**. You get `https://ipnet-usa-YOU.workers.dev`. No variables, nothing to fill. |
| **3** | In your repo, open **`worker.txt`** → write that ONE line (`ipnet-usa-YOU.workers.dev`) → Commit. The **First setup** action builds your `sub.txt` once. That's it — nothing runs every minute. |

Check it: open `https://YOUR-WORKER.workers.dev/` — green ✅ Connected page. Mobile: use the `sub.txt` link from your repo's README live block.

---

## 2️⃣ Run on Windows

| Step | What to do |
|:---:|---|
| **1** | Click [**IPNET.exe**](https://github.com/X5Coder/IPNET/releases/latest/download/IPNET.exe) — it downloads directly. Run it. |
| **2** | Paste **your repo link** into the app → click **Start**. Chrome opens with a US IP. |
| **3** | Every time after: your link is saved automatically — just click **Start**. |

---

## 3️⃣ Run on Android

| Step | What to do |
|:---:|---|
| **1** | Click [**v2rayNG.apk**](https://github.com/2dust/v2rayNG/releases/download/2.2.6/v2rayNG_2.2.6_arm64-v8a.apk) to download, then install it. (No second app needed - one link does everything.) |
| **2** | Open the top-left menu → **Subscription group setting** → tap **+** and fill in the fields below. |

**Subscription fields:**

| Field | Value |
|---|---|
| `remarks` | `IPNET` |
| `Optional URL` | Your subscription link, e.g. `https://raw.githubusercontent.com/YOU/YOUR-REPO/main/sub.txt`<br>*(replace `YOU/YOUR-REPO` with your own repo)* |
| `Enable update` | ✅ ON |
| `Enable automatic update` | ✅ ON — interval `60` |

Then tap **✓** to save.

| Step | What to do |
|:---:|---|
| **4** | On the main screen tap **⋮** → **Update subscription** → you will see one config: `IPNET-USA` (VLESS over your own Worker, TLS+WebSocket). |
| **5** | Tap `IPNET-USA` → tap **▶** → allow the VPN permission. No other app, no peers, no settings. |
| **6** | Verify it worked at [ipleak.net](https://ipleak.net/) — it usually shows **United States** (Cloudflare egress; see note below). |
| **7** | If it stops working later: **⋮** → **Update subscription** → reconnect. (Your Worker address is fixed — it never rotates.) |

> Honest note: Cloudflare egress IPs are registered US in most cases, so `ipleak.net` usually shows **United States**, but a small share of requests may exit via EU colos. If you need a guaranteed US datacenter IP, move the same setup to Oracle Ashburn free tier later — the app flow stays identical.

---

## ⭐ Support the Project

<div align="center">

If IPNET is useful to you, please **star the repo** — it takes 5 seconds and helps keep the project alive 🙏

<a href="https://github.com/X5Coder/IPNET"><img src="https://img.shields.io/github/stars/X5Coder/IPNET?style=for-the-badge&logo=github&color=ffd700&label=Star%20IPNET&labelColor=24292e" alt="Star IPNET"></a>

<br><br>

<a href="https://github.com/X5Coder/IPNET"><img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=18&duration=3000&pause=1000&color=666666&center=true&vCenter=true&width=600&lines=Original%3A+github.com%2FX5Coder%2FIPNET;by+X5Coder+%E2%80%A2+Do+not+remove+credits;Tutorials+on+YouTube+%E2%96%B6+Kareem+X5Coder" alt="credits"></a>

<br>

<a href="https://www.youtube.com/@Kareem-X5Coder"><img src="https://img.shields.io/badge/YouTube-Kareem_X5Coder-ff0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube"></a>
<a href="https://github.com/X5Coder/IPNET"><img src="https://img.shields.io/badge/Repo-IPNET_Original-111111?style=for-the-badge&logo=github&logoColor=white" alt="Original repo"></a>

</div>
