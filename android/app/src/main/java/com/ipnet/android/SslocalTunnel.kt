package com.ipnet.android

import android.content.Context
import android.os.ParcelFileDescriptor
import java.io.File
import org.json.JSONObject

/**
 * Minimal data plane: shadowsocks-rust `sslocal` in TUN mode (~4MB).
 *
 * Chain: TUN fd (from VpnService.Builder) -> sslocal --protocol tun ->
 * Shadowsocks to bore.pub:port (USA). TCP+UDP (incl. DNS) go through the
 * shadowsocks UDP relay, which our sing-box server supports — no udpgw,
 * no tun2socks, no extra daemons.
 *
 * Loop protection: our own UID is excluded from the VPN via
 * Builder.addDisallowedApplication(), so sslocal's sockets (same UID)
 * always bypass the TUN. No per-socket protect() needed.
 *
 * Binary provenance: built in CI from shadowsocks-rust source
 * (cargo-ndk, arm64-v8a, features: local,local-tun,aead-cipher) and
 * staged at assets/bin/arm64-v8a/sslocal. Extracted to filesDir on
 * first run (assets lose the exec bit, so we chmod here).
 *
 * NOTE: the two tun_* config keys below mirror sslocal's documented
 * tun options; if a first device run reports an unknown key in logcat,
 * the fix is confined to buildTunConfig().
 */
class SslocalTunnel(private val ctx: Context) {
    private var proc: Process? = null

    fun buildTunConfig(
        tunFdFile: String, host: String, port: Int,
        password: String, method: String,
    ): String = JSONObject()
        .put("server", host)
        .put("server_port", port)
        .put("password", password)
        .put("method", method)
        .put("protocol", "tun")
        .put("tun_interface_name", "ipnet0")
        .put("tun_interface_address", "10.8.0.2")
        .put("tun_interface_destination", "10.8.0.1")
        .put("tun_device_fd_from_path", tunFdFile)
        .toString()

    fun start(tun: ParcelFileDescriptor, host: String, port: Int, password: String, method: String) {
        stop()
        val dir = File(ctx.filesDir, "bin").apply { mkdirs() }
        val bin = File(dir, "sslocal")
        if (!bin.exists()) {
            ctx.assets.open("bin/arm64-v8a/sslocal").use { inp ->
                bin.outputStream().use { out -> inp.copyTo(out) }
            }
            Runtime.getRuntime().exec(arrayOf("chmod", "755", bin.absolutePath)).waitFor()
        }
        val fdFile = File(dir, "tunfd.txt")
        fdFile.writeText(tun.fd.toString())
        val confFile = File(dir, "sslocal.json")
        confFile.writeText(buildTunConfig(fdFile.absolutePath, host, port, password, method))
        proc = ProcessBuilder(bin.absolutePath, "-c", confFile.absolutePath)
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
