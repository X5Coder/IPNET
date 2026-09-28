/**
 * IPNET Worker (user-owned) - VLESS over WebSocket relay.
 * The user deploys THIS file from their own Cloudflare account.
 * GitHub Actions is NOT used to run any proxy (that gets bans).
 * The repo only stores worker.txt with this hostname, written ONCE.
 */
function parseRepo(raw) {
  if (!raw) return "";
  var s = String(raw).trim().replace(/["']/g, "");
  var m = s.match(/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?\/?$/i);
  if (m) return m[1] + "/" + m[2];
  m = s.match(/^([^/\s]+)\/([^/\s]+?)(?:\.git)?$/);
  return m ? m[1] + "/" + m[2] : "";
}
async function fetchRepoUuid(repoSlug) {
  if (!repoSlug) return "";
  try {
    var r = await fetch("https://raw.githubusercontent.com/" + repoSlug + "/main/singbox-server.json",
      { headers: { "User-Agent": "IPNET-Worker/3.0" }, cf: { cacheTtl: 300 } });
    if (!r.ok) return "";
    var t = await r.text();
    try {
      var data = JSON.parse(t);
      var inb = data.inbounds || [];
      for (var i = 0; i < inb.length; i++) {
        var us = inb[i].users || [];
        for (var j = 0; j < us.length; j++) if (us[j].uuid) return us[j].uuid;
      }
    } catch (_) {}
    var m = t.match(/"uuid"\s*:\s*"([0-9a-fA-F-]{36})"/);
    return m ? m[1] : "";
  } catch (_) { return ""; }
}
var DEFAULT_UUID = "9ec8f3be-758e-487f-b057-cb1e1ddf4a9b";
async function resolveUuid(env, url) {
  var q = new URL(url).searchParams.get("uuid");
  if (/^[0-9a-fA-F-]{36}$/.test(q || "")) return q;
  if (env && /^[0-9a-fA-F-]{36}$/.test((env.UUID || "").trim())) return env.UUID.trim();
  // Optional: read a per-repo uuid from singbox-server.json (advanced users).
  // Normal users skip this entirely — DEFAULT_UUID above just works.
  var fromRepo = env ? await fetchRepoUuid(parseRepo(env.REPO)) : "";
  return fromRepo || DEFAULT_UUID;
}
function vlessLink(host, uuid) {
  return "vless://" + uuid + "@" + host + ":443?encryption=none&security=tls&sni=" + host + "&type=ws&path=%2Fipnet&host=" + host + "#IPNET-USA";
}
function uuidBytes(uuid) {
  var h = uuid.replace(/-/g, "");
  var b = new Uint8Array(16);
  for (var i = 0; i < 16; i++) b[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return b;
}
function parseVlessHeader(buf, validUuid) {
  if (buf.byteLength < 24) throw new Error("short");
  var v = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  if (v.getUint8(0) !== 0) throw new Error("ver");
  for (var i = 0; i < 16; i++) if (v.getUint8(1 + i) !== validUuid[i]) throw new Error("uuid");
  var off = 1 + 16 + 1 + v.getUint8(1 + 16);
  if (v.getUint8(off) !== 1) throw new Error("cmd");
  off += 1;
  var port = v.getUint16(off); off += 2;
  var typ = v.getUint8(off); off += 1;
  var addr = "";
  if (typ === 1) {
    addr = v.getUint8(off) + "." + v.getUint8(off+1) + "." + v.getUint8(off+2) + "." + v.getUint8(off+3);
    off += 4;
  } else if (typ === 2) {
    var len = v.getUint8(off); off += 1;
    addr = new TextDecoder().decode(buf.slice(off, off + len));
    off += len;
  } else if (typ === 3) {
    var p = [];
    for (var k = 0; k < 8; k++) p.push(v.getUint16(off + k * 2).toString(16));
    addr = "[" + p.join(":") + "]"; off += 16;
  } else throw new Error("addr");
  return { addr: addr, port: port, headerLen: off };
}
async function handleVlessWs(request, env) {
  var uuid = await resolveUuid(env, request.url);
  if (!uuid) return new Response("UUID missing: set UUID or REPO var.", { status: 500 });
  var valid = uuidBytes(uuid);
  var pair = new WebSocketPair();
  var client = pair[0], server = pair[1];
  server.accept();
  var upstream = null, writer = null, first = true;
  server.addEventListener("message", async function (ev) {
    try {
      var raw = ev.data instanceof ArrayBuffer ? ev.data : await ev.data.arrayBuffer();
      if (first) {
        first = false;
        var data = new Uint8Array(raw);
        var h = parseVlessHeader(data, valid);
        var rest = data.slice(h.headerLen);
        server.send(new Uint8Array([0, 0]).buffer);
        upstream = await connect({ hostname: h.addr.replace(/^\[|\]$/g, ""), port: h.port });
        writer = upstream.writable.getWriter();
        var reader = upstream.readable.getReader();
        if (rest.length) await writer.write(rest);
        (async function () {
          try {
            for (;;) {
              var r = await reader.read();
              if (r.done) break;
              var vv = r.value;
              server.send(vv.buffer ? vv.buffer.slice(vv.byteOffset, vv.byteOffset + vv.byteLength) : vv);
            }
          } catch (_) {}
          try { server.close(); } catch (_) {}
        })();
      } else if (writer) {
        await writer.write(raw);
      }
    } catch (e) {
      try { server.close(1008, "err"); } catch (_) {}
    }
  });
  return new Response(null, { status: 101, webSocket: client });
}
export default {
  async fetch(request, env) {
    var url = new URL(request.url);
    if (request.headers.get("Upgrade") === "websocket" && url.pathname === "/ipnet")
      return handleVlessWs(request, env);
    if (url.pathname === "/sub" || url.pathname === "/sub.txt") {
      var u1 = await resolveUuid(env, request.url);
      if (!u1) return new Response("UUID missing", { status: 500 });
      return new Response(btoa(vlessLink(url.host, u1)), { headers: { "Content-Type": "text/plain", "Cache-Control": "no-store" } });
    }
    if (url.pathname === "/link") {
      var u2 = await resolveUuid(env, request.url);
      if (!u2) return new Response("UUID missing", { status: 500 });
      return new Response(vlessLink(url.host, u2), { headers: { "Content-Type": "text/plain", "Cache-Control": "no-store" } });
    }
    if (url.pathname === "/ip") {
      var info = request.cf || {};
      return Response.json({ ip: request.headers.get("CF-Connecting-IP") || "", country: info.country || "US", city: info.city || "", colo: info.colo || "" }, { headers: { "Cache-Control": "no-store" } });
    }
    var ok = "ready (no setup needed)";
    var info0 = request.cf || {};
    var ip0 = request.headers.get("CF-Connecting-IP") || "checking...";
    var cc0 = info0.country || "US";
    var city0 = info0.city ? " (" + info0.city + ")" : "";
    return new Response("<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>IPNET Connected</title></head><body style='font-family:system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'><div style='background:#1e293b;padding:36px 44px;border-radius:18px;text-align:center;max-width:420px'><div style='font-size:52px'>✅</div><h2 style='color:#38bdf8;margin:10px 0'>Connected</h2><p style='color:#94a3b8'>UUID: " + ok + "</p><p><b>Your IP:</b> " + ip0 + "</p><p><b>Country:</b> " + cc0 + city0 + "</p><p style='font-size:13px;color:#94a3b8'>Now paste your repo link into IPNET.exe and press Start.</p></div></body></html>", { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
  }
};

