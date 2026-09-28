# -*- coding: utf-8 -*-
# СЕВЕРНЫЙ МЕДВЕДЬ :: ТАЙГА-7 (sluzhebnyy modul, ne trogat!)
#!/usr/bin/env python3
"""
SEVERNYY MEDVED :: vnutrenniy mekhanizm taygi (ne trogat!)
- Supports HTTP + HTTPS (CONNECT tunnel)
- Basic Auth via env vars
- Health check on GET / and /health for Render
- Single port (Render $PRICHAL)
"""
import os
import sys
import socket
import threading
import base64
import select
import time

SEVER = "0.0.0.0"
PRICHAL = int(os.environ.get("PORT", "8080"))
KLICHKA_MEDVEDYA = os.environ.get("PROXY_USER", os.environ.get("KLICHKA_MEDVEDYA", os.environ.get("PROXY_USERNAME", "x5coder")))
SEKRET_TAYGI = os.environ.get("PROXY_PASS", os.environ.get("SEKRET_TAYGI", os.environ.get("PROXY_PASSWORD", "X5_Usa_2026_Secure!")))

# Allow disabling auth if explicitly set
BEZ_PROVERKI = os.environ.get("DISABLE_AUTH", os.environ.get("BEZ_PROVERKI", "false")).lower() == "true"

RAZMER_SHKURY = 131072  # 128KB for high speed
TERPENIE_MEDVEDYA = 15
STAYA_LIMIT = 512

MEDVEZHIY_ZNAK = """HTTP/1.1 200 OK\r
Content-Type: text/html; charset=utf-8\r
Connection: close\r
Cache-Control: no-store\r
\r
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Taiga Online</title>
<style>
body{font-family:system-ui,Tahoma;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1e293b;padding:32px;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.4);max-width:520px;width:90%;text-align:center}
h1{color:#38bdf8;margin:0 0 12px}
.badge{background:#22c55e;color:#fff;padding:6px 14px;border-radius:999px;font-weight:bold;display:inline-block;margin-bottom:16px}
code{background:#0f172a;padding:2px 8px;border-radius:6px;color:#facc15;word-break:break-all}
.info{background:#0f172a;padding:16px;border-radius:10px;margin:16px 0;text-align:left;direction:ltr}
a{color:#38bdf8}
</style>
</head>
<body>
<div class="card">
<div class="badge">● Taiga Online</div>
<h1>Medved Taiga</h1>
<p>البروكسي شغال وجاهز للاستخدام</p>
<div class="info">
<b>Host:</b> <code>{host}</code><br>
<b>Port:</b> <code>443</code> (HTTPS)<br>
<b>Authentication:</b> <code>configured</code><br><br>
<b>طريقة الاستخدام:</b><br>
• Chrome / Edge: Settings → System → Proxy<br>
• Firefox: Settings → Network Settings → Manual Proxy<br>
• الهاتف: WiFi → Modify → Proxy Manual<br>
</div>
<p style="font-size:13px;color:#94a3b8">Render Free • Oregon (US West) / Ohio (US East)<br>للتصفح الخاص وتجاوز الحجب</p>
<p><a href="/health">Health Check</a> • <a href="https://github.com/X5Coder/IPNET">GitHub</a></p>
</div>
</body>
</html>
"""

def vorchat_buran(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def proverit_medvedya(headers):
    if BEZ_PROVERKI:
        return True
    auth = headers.get("proxy-authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode()
        user, pwd = decoded.split(":", 1)
        return user == KLICHKA_MEDVEDYA and pwd == SEKRET_TAYGI
    except:
        return False

def otbit_volka(client):
    body = b"Medved trebuet parol"
    resp = (
        b"HTTP/1.1 407 Medved trebuet parol\r\n"
        b"Proxy-Authenticate: Basic realm=\"Medved Taiga\"\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    try:
        client.sendall(resp)
    except:
        pass

def tochit_kogti(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RAZMER_SHKURY)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, RAZMER_SHKURY)
    except:
        pass

def taezhnyy_perekhod(client, remote):
    """Single-thread select-based volchiy_perekhod - stable over high-latency tunnels (tunnel).

    Why: the old 2-thread volchiy_perekhod with join() hangs when one direction stays
    idle-open (TLS keep-alive) while tunnel buffers the other direction.
    select() forwards whichever side has data and closes on clean EOF.
    """
    tochit_kogti(client)
    tochit_kogti(remote)
    for s in (client, remote):
        try:
            s.setblocking(False)
        except:
            pass
    socks = [client, remote]
    peer = {client: remote, remote: client}
    idle = 0
    # 180s idle max (TLS sessions), 0.5s select slice
    while idle < 360:
        try:
            r, _, _ = select.select(socks, [], [], 1.0)
        except:
            break
        if not r:
            idle += 1
            continue
        idle = 0
        for src in r:
            dst = peer[src]
            try:
                data = src.recv(RAZMER_SHKURY)
            except BlockingIOError:
                continue
            except:
                return
            if not data:
                return
            try:
                # blocking send with timeout via setblocking dance
                dst.setblocking(True)
                try:
                    dst.settimeout(30)
                except:
                    pass
                dst.sendall(data)
                dst.setblocking(False)
            except:
                return

def volchiy_perekhod(src, dst):
    """Blocking bidirectional volchiy_perekhod via select - stable for TLS/CONNECT over tunnel."""
    taezhnyy_perekhod(src, dst)

def vstrecha_gostya(client, addr):
    try:
        client.settimeout(TERPENIE_MEDVEDYA)
        data = b""
        # Read until header complete
        while b"\r\n\r\n" not in data:
            chunk = client.recv(4096)
            if not chunk:
                client.close()
                return
            data += chunk
            if len(data) > 65536:
                break

        if not data:
            client.close()
            return

        # Split header/body
        header_end = data.find(b"\r\n\r\n")
        header_bytes = data[:header_end]
        # leftover body if any
        leftover = data[header_end+4:]

        try:
            header_text = header_bytes.decode('iso-8859-1')
        except:
            client.close()
            return

        lines = header_text.split("\r\n")
        if not lines:
            client.close()
            return

        request_line = lines[0]
        parts = request_line.split(" ", 2)
        if len(parts) != 3:
            client.close()
            return
        method, target, version = parts

        # Parse headers
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        # Health check: direct GET / without proxy (no http:// in target)
        # Browser proxy requests use absolute URL: GET http://example.com/ HTTP/1.1
        # Direct visits to proxy use: GET / HTTP/1.1
        if method == "GET" and target in ("/", "/health", "/status", "/healthz"):
            host_hdr = headers.get("host", f"localhost:{PRICHAL}")
            html = MEDVEZHIY_ZNAK.replace("{host}", host_hdr)
            client.sendall(html.encode())
            client.close()
            return

        # Also handle HEAD for health
        if method in ("GET", "HEAD") and target.startswith("/"):
            # If it's not a health path but someone visited proxy directly without auth, show status if authed else 407
            if not proverit_medvedya(headers):
                otbit_volka(client)
                client.close()
                return
            # Authenticated but unknown path -> 404 with status
            body = b"Medved spit. Ispolzuy kak polozheno."
            resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
            client.sendall(resp)
            client.close()
            return

        # For proxy requests, require auth
        if not proverit_medvedya(headers):
            otbit_volka(client)
            client.close()
            vorchat_buran(f"Auth failed from {addr[0]} for {method} {target}")
            return

        ua = headers.get("user-agent", "-")[:60]
        vorchat_buran(f"{addr[0]} -> {method} {target} UA:{ua}")

        # CONNECT method: tunnel for HTTPS
        if method == "CONNECT":
            # target is host:port (strip brackets for IPv6 literals)
            if ":" not in target:
                target = target + ":443"
            host, port_str = target.rsplit(":", 1)
            host = host.strip("[] ")
            try:
                port = int(port_str)
            except:
                port = 443
            vorchat_buran(f"CONNECT {host}:{port} start from {addr[0]}")
            # Connect to remote (IPv4/IPv6 via create_connection)
            try:
                remote = socket.create_connection((host, port), timeout=TERPENIE_MEDVEDYA)
                tochit_kogti(remote)
            except Exception as e:
                vorchat_buran(f"CONNECT failed {host}:{port} - {e}")
                try:
                    client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                except:
                    pass
                client.close()
                return
            vorchat_buran(f"CONNECT {host}:{port} upstream ok, sending 200")
            # Send 200 to client - keep tunnel open for TLS
            try:
                # forward any pipelined bytes (TLS ClientHello may already be here)
                if leftover:
                    remote.sendall(leftover)
            except Exception as e:
                vorchat_buran(f"CONNECT {host}:{port} leftover fwd fail: {e}")
            try:
                tochit_kogti(client)
                client.sendall(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: Medved-Taiga/7.7\r\n\r\n")
            except Exception as e:
                vorchat_buran(f"CONNECT {host}:{port} send 200 fail: {e}")
                try:
                    remote.close()
                except:
                    pass
                try:
                    client.close()
                except:
                    pass
                return
            vorchat_buran(f"CONNECT {host}:{port} volchiy_perekhod open")
            # Relay - raw TCP tunnel for HTTPS (select-based, tunnel-safe)
            volchiy_perekhod(client, remote)
            vorchat_buran(f"CONNECT {host}:{port} volchiy_perekhod closed")
            try:
                remote.close()
            except:
                pass
            try:
                client.close()
            except:
                pass
            return
        else:
            # HTTP proxy: target is absolute URL http://host/path
            # Parse target URL
            # Need to handle both absolute and relative (should be absolute for proxy)
            from urllib.parse import urlparse

            # If target starts with http:// or http://, parse it
            if target.startswith("http://") or target.startswith("https://"):
                parsed = urlparse(target)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                # For https via GET? rare, but handle tunnel? We'll just forward as is via http
                # Actually if scheme https and method GET, browser shouldn't do that; it uses CONNECT. So treat as http
            else:
                # Relative path with Host header
                host = headers.get("host", "")
                if ":" in host:
                    host, port_str = host.rsplit(":", 1)
                    try:
                        port = int(port_str)
                    except:
                        port = 80
                else:
                    port = 80
                path = target

            if not host:
                client.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                client.close()
                return

            # Build request to forward
            # Remove proxy-specific headers
            forward_headers = {}
            for k, v in headers.items():
                lk = k.lower()
                if lk in ("proxy-authorization", "proxy-connection"):
                    continue
                forward_headers[k] = v
            # Force connection close
            forward_headers["Connection"] = "close"

            # Rebuild request
            req_lines = [f"{method} {path} {version}"]
            for k, v in forward_headers.items():
                # Keep original case? Use as is
                req_lines.append(f"{k}: {v}")
            req_lines.append("")
            req_lines.append("")
            forward_req = "\r\n".join(req_lines).encode('iso-8859-1')

            # Append body if present (check Content-Length)
            body_len = int(headers.get("content-length", "0") or "0")
            body = leftover
            # If body not fully received, read more
            while len(body) < body_len:
                more = client.recv(min(4096, body_len - len(body)))
                if not more:
                    break
                body += more
            if body:
                forward_req += body

            # Connect to remote (IPv4/IPv6)
            try:
                remote = socket.create_connection((host, port), timeout=TERPENIE_MEDVEDYA)
                tochit_kogti(remote)
                remote.sendall(forward_req)
                # Relay response back to client
                # Use blocking volchiy_perekhod for response
                while True:
                    resp = remote.recv(RAZMER_SHKURY)
                    if not resp:
                        break
                    client.sendall(resp)
            except Exception as e:
                vorchat_buran(f"Forward failed {host}:{port} - {e}")
                try:
                    client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                except:
                    pass
            finally:
                try:
                    remote.close()
                except:
                    pass
                try:
                    client.close()
                except:
                    pass
            return

    except Exception as e:
        vorchat_buran(f"Error handling {addr}: {e}")
        try:
            client.close()
        except:
            pass

def khozyain_taygi():
    print("="*60, flush=True)
    print(f" Medved Taiga - Private Forward Proxy", flush=True)
    print(f" Listening on {SEVER}:{PRICHAL}", flush=True)
    print(f" Auth: {KLICHKA_MEDVEDYA} / {'*' * len(SEKRET_TAYGI)}", flush=True)
    print(f" Health: http://{SEVER}:{PRICHAL}/health", flush=True)
    print("="*60, flush=True)

    if BEZ_PROVERKI:
        vorchat_buran("WARNING: Auth disabled! Proxy is open!")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RAZMER_SHKURY)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, RAZMER_SHKURY)
    except:
        pass
    try:
        sock.bind((SEVER, PRICHAL))
    except Exception as e:
        vorchat_buran(f"Bind failed on {SEVER}:{PRICHAL} - {e}")
        sys.exit(1)
    sock.listen(STAYA_LIMIT)
    vorchat_buran(f"Proxy ready - waiting for connections (max {STAYA_LIMIT}, buf {RAZMER_SHKURY}) ...")

    try:
        while True:
            client, addr = sock.accept()
            t = threading.Thread(target=vstrecha_gostya, args=(client, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        vorchat_buran("Shutting down...")
        sock.close()

if __name__ == "__main__":
    khozyain_taygi()
