package com.ipnet.android

import android.os.ParcelFileDescriptor
import hev.htproxy.TProxyService as Hev
import java.io.File

/**
 * TUN data plane, in-process via hev-socks5-tunnel JNI.
 *
 * Why this instead of exec'ing a binary: a TUN fd cannot cross a process
 * boundary by number (that silent failure is exactly why the browser kept
 * working normally). Here the fd stays in our process and goes straight
 * into TProxyStartService(configPath, fd) — the documented contract also
 * used by Orbot/SocksTun. TCP+UDP (incl. DNS) ride the SOCKS5 UDP relay
 * served by our local ss-local -> sing-box server.
 */
class HevTunnel {
    @Volatile
    var running = false
        private set

    fun buildConfig(): String = """
        tunnel:
          mtu: 9000
        socks5:
          address: 127.0.0.1
          port: 1080
          udp: 'udp'
        misc:
          log-level: 'warn'
    """.trimIndent()

    /** Blocking call — run on a background thread. Returns true if up. */
    fun start(confDir: File, tun: ParcelFileDescriptor): Boolean {
        val conf = File(confDir, "hev.yml")
        conf.writeText(buildConfig())
        running = Hev.TProxyStartService(conf.absolutePath, tun.fd)
        return running
    }

    fun stop() {
        try {
            Hev.TProxyStopService()
        } catch (_: Exception) { }
        running = false
    }

    fun isRunning(): Boolean = try {
        Hev.TProxyIsRunning()
    } catch (_: Exception) {
        running
    }
}
