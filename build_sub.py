"""Build sub.txt + android.txt + README live block from server host.
Usage: python3 build_sub.py <host>   (run by publish.yml)
Safe: static files only, no proxy, no tunnel.
Render mode (xxx.onrender.com): HTTP proxy login for Chrome/Firefox +
phone apps (same shared user/pass). Worker mode: vless link (legacy)."""
import base64, json, os, re, sys

host = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
host = re.sub(r"^https?://", "", host).split("/")[0]
is_render = host.endswith(".onrender.com")
is_worker = re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.workers\.dev$", host)
if not (is_render or is_worker):
    print("bad host:", host)
    sys.exit(0)

if is_render:
    # Phone/PC manual proxy: host + 443 + shared login (same as x5proxy).
    http_link = "http://x5coder:X5_Usa_2026_Secure!@%s:443" % host
    open("android.txt", "w", encoding="utf-8").write(http_link)
    open("sub.txt", "w", encoding="utf-8").write(
        base64.b64encode(("IPNET-USA Render proxy\n" + http_link + "\n").encode()).decode())
    link_line = http_link
    kind = "HTTP proxy (Render Oregon USA, login built-in)"
else:
    uuid = json.load(open("singbox-server.json", encoding="utf-8"))["inbounds"][0]["users"][0]["uuid"]
    link_line = ("vless://%s@%s:443?encryption=none&security=tls"
                 "&sni=%s&type=ws&path=%%2Fipnet&host=%s#IPNET-USA" % (uuid, host, host, host))
    open("android-vless.txt", "w", encoding="utf-8").write(link_line)
    open("sub.txt", "w", encoding="utf-8").write(base64.b64encode(link_line.encode()).decode())
    kind = "VLESS+WS+TLS via your own Worker"

repo = os.environ.get("GITHUB_REPOSITORY", "YOU/YOUR-REPO")
server_line = "Render: https://%s" % host if is_render else "Worker: https://%s" % host
block = ("<!--IPNET-LIVE-START-->\n## Live connection (auto-updated, copy from here)\n\n"
         "- Repo: https://github.com/%s\n- %s\n\n"
         "- Phone/PC link (%s):\n```\n%s\n```\n\n"
         "- Subscription (fixed forever, auto-updates):\n```\nhttps://raw.githubusercontent.com/%s/main/sub.txt\n```\n"
         "<!--IPNET-LIVE-END-->" % (repo, server_line, kind, link_line, repo))
s = open("README.md", encoding="utf-8").read()
pat = re.compile(r"<!--IPNET-LIVE-START-->.*?<!--IPNET-LIVE-END-->", re.S)
s = pat.sub(block, s, count=1) if pat.search(s) else s + "\n" + block + "\n"
open("README.md", "w", encoding="utf-8").write(s)
print("subscription built for", host)
