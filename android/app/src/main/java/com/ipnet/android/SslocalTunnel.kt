package com.ipnet.android

import android.content.Context
import android.os.ParcelFileDescriptor
import java.io.File
import org.json.JSONObject

/**
 * Minimal SOCKS plane: shadowsocks-rust `sslocal` (~4MB).
 *
 * Plain SOCKS5 on 127.0.0.1:1080 with UDP relay on (-u): the TUN layer
 * (hev, in-process) forwards everything here, ss-local carries it to
 * bore.pub:port (USA). No TUN duties here, so no fd passing — an exec'd
 * child only needs sockets, which bypass the VPN via
 * addDisallowedApplication(self).
 *
 * Binary provenance: built in CI from shadowsocks-rust source
 * (cargo-ndk, arm64-v8a, features: local,aead-cipher) and staged at
 * assets/bin/arm64-v8a/sslocal. Extracted to filesDir on first run
 * (assets lose the exec bit, so we chmod here).
 */
class SslocalTunnel(private val ctx: Context) {
    private var proc: Process? = null

    fun buildSocksConfig(host: String, port: Int, password: String, method: String): String =
        JSONObject()
            .put("server", host)
            .put("server_port", port)
            .put("password", password)
            .put("method", method)
            .put("local_address", "127.0.0.1")
            .put("local_port", 1080)
            .toString()

    fun start(host: String, port: Int, password: String, method: String) {
        stop()
        val dir = File(ctx.filesDir, "bin").apply { mkdirs() }
        val bin = File(dir, "sslocal")
        if (!bin.exists()) {
            ctx.assets.open("bin/arm64-v8a/sslocal").use { inp ->
                bin.outputStream().use { out -> inp.copyTo(out) }
            }
            Runtime.getRuntime().exec(arrayOf("chmod", "755", bin.absolutePath)).waitFor()
        }
        val confFile = File(dir, "sslocal.json")
        confFile.writeText(buildSocksConfig(host, port, password, method))
        proc = ProcessBuilder(bin.absolutePath, "-c", confFile.absolutePath, "-u")
            .directory(dir)
            .redirectErrorStream(true)
            .start()
        // Drain output so a full pipe never blocks the daemon; dies with us.
        Thread({
            try {
                proc?.inputStream?.bufferedReader()?.forEachLine { }
            } catch (_: Exception) { }
        }, "sslocal-log").apply { isDaemon = true }.start()
        Thread.sleep(1500)
        val p = proc
        if (p == null || !p.isAlive) {
            throw RuntimeException("sslocal exited immediately - check logcat for its stderr")
        }
    }

    fun stop() {
        try {
            proc?.destroy()
            proc?.waitFor()
        } catch (_: Exception) { }
        proc = null
    }
}
