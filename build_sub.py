"""Build sub.txt + android-vless.txt + README live block from worker host.
Usage: python3 build_sub.py <worker-host>   (run by publish.yml)
Safe: static files only, no proxy, no tunnel."""
import base64, json, os, re, sys

host = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
host = re.sub(r"^https?://", "", host).split("/")[0]
if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.workers\.dev$", host):
    print("bad worker host:", host)
    sys.exit(0)

uuid = json.load(open("singbox-server.json", encoding="utf-8"))["inbounds"][0]["users"][0]["uuid"]
link = ("vless://%s@%s:443?encryption=none&security=tls"
        "&sni=%s&type=ws&path=%%2Fipnet&host=%s#IPNET-USA" % (uuid, host, host, host))
open("android-vless.txt", "w", encoding="utf-8").write(link)
open("sub.txt", "w", encoding="utf-8").write(base64.b64encode(link.encode()).decode())

repo = os.environ.get("GITHUB_REPOSITORY", "YOU/YOUR-REPO")
block = ("<!--IPNET-LIVE-START-->\n## Live connection (auto-updated, copy from here)\n\n"
         "- Repo: https://github.com/%s\n- Worker: https://%s\n\n"
         "- v2rayNG link (copy/QR, VLESS+WS+TLS via your own Worker):\n```\n%s\n```\n\n"
         "- Subscription (fixed forever, auto-updates):\n```\nhttps://raw.githubusercontent.com/%s/main/sub.txt\n```\n"
         "<!--IPNET-LIVE-END-->" % (repo, host, link, repo))
s = open("README.md", encoding="utf-8").read()
pat = re.compile(r"<!--IPNET-LIVE-START-->.*?<!--IPNET-LIVE-END-->", re.S)
s = pat.sub(block, s, count=1) if pat.search(s) else s + "\n" + block + "\n"
open("README.md", "w", encoding="utf-8").write(s)
print("subscription built for", host)
