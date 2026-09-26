package com.ipnet.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import kotlinx.coroutines.*
import java.io.File

/**
 * Device-level VPN that actually moves packets:
 *
 *  1. Builder(): TUN 10.8.0.2/32, route 0.0.0.0/0, DNS 1.1.1.1, plus
 *     addDisallowedApplication(self) so our own sockets bypass the TUN.
 *  2. ss-local (child process, plain SOCKS+UDP relay on 127.0.0.1:1080)
 *     carries traffic to bore.pub:port (USA).
 *  3. hev-socks5-tunnel (IN-PROCESS JNI, fd passed as int — the only
 *     way a TUN fd can be shared) pumps TUN <-> SOCKS, TCP+UDP.
 *  4. EndpointWorker (WorkManager, 30 min) restarts us on renewal.
 *
 * Every step writes to the Prefs trace so the diagnostics screen shows
 * exactly where a start died — no logcat needed.
 */
class ProxyVpnService : VpnService() {
    companion object {
        const val ACTION_STOP = "com.ipnet.android.STOP_VPN"
        const val ACTION_SOCKS = "com.ipnet.android.START_SOCKS"
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var tun: ParcelFileDescriptor? = null
    private var ss: SslocalTunnel? = null
    private var hev: HevTunnel? = null

    private fun tr(s: String) = Prefs.trace(this, s)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        tr("onStart action=${intent?.action}")
        if (intent?.action == ACTION_STOP) {
            stopAll()
            stopSelf()
            return START_NOT_STICKY
        }
        try {
            startForegroundWithNotification()
            tr("foreground ok")
        } catch (t: Throwable) {
            Prefs.saveError(this, "notification: ${t.message}")
            stopSelf()
            return START_NOT_STICKY
        }
        val host = intent?.getStringExtra("ss_host").orEmpty()
        val port = intent?.getIntExtra("ss_port", 0) ?: 0
        val password = intent?.getStringExtra("ss_password").orEmpty()
        val method = intent?.getStringExtra("ss_method") ?: "aes-256-gcm"
        if (host.isEmpty() || port == 0 || password.isEmpty()) {
            Prefs.saveError(this, "empty extras")
            stopSelf()
            return START_NOT_STICKY
        }
        Prefs.save(this, intent?.getStringExtra("owner") ?: Prefs.load(this)["owner"].orEmpty(),
            intent?.getStringExtra("repo") ?: Prefs.load(this)["repo"].orEmpty(),
            host, port, password, method)
        if (intent?.action == ACTION_SOCKS) {
            // Socks-only mode: NO Tunis, NO system VPN consent needed.
            // ss-local listens on 127.0.0.1:1080; apps with manual proxy
            // settings (e.g. Telegram) point at it directly.
            scope.launch {
                try {
                    stopAll()
                    Prefs.clearError(this@ProxyVpnService)
                    tr("socks-only starting")
                    SslocalTunnel(this@ProxyVpnService).also { ss = it }
                        .start(host, port, password, method)
                    tr("socks-only alive on 127.0.0.1:1080")
                } catch (t: Throwable) {
                    Prefs.saveError(this@ProxyVpnService,
                        t.message ?: t.javaClass.simpleName)
                    tr("SOCKS DIED: ${t.javaClass.simpleName}: ${t.message}")
                    stopAll()
                    stopSelf()
                }
            }
            return START_STICKY
        }
        scope.launch {
            try {
                stopAll()
                Prefs.clearError(this@ProxyVpnService)
                tr("building TUN")
                tun = Builder()
                    .addAddress("10.8.0.2", 32)
                    .addRoute("0.0.0.0", 0)
                    .addDnsServer("1.1.1.1")
                    .addDnsServer("8.8.8.8")
                    .addDisallowedApplication(packageName)
                    .setSession("IPNET USA")
                    .setBlocking(true)
                    .establish()
                val fd = tun ?: throw RuntimeException("TUN establish=null")
                tr("TUN fd=${fd.fd}")
                val ssl = SslocalTunnel(this@ProxyVpnService).also { ss = it }
                ssl.start(host, port, password, method)
                tr("ss-local alive")
                val h = HevTunnel().also { hev = it }
                val confDir = File(filesDir, "bin").apply { mkdirs() }
                tr("hev starting")
                val up = withContext(Dispatchers.IO) { h.start(confDir, fd) }
                tr("hev returned=$up")
                if (!up) throw RuntimeException("hev refused")
            } catch (t: Throwable) {
                Prefs.saveError(this@ProxyVpnService,
                    t.message ?: t.javaClass.simpleName)
                tr("DIED: ${t.javaClass.simpleName}: ${t.message}")
                stopAll()
                stopSelf()
            }
        }
        EndpointWorker.schedule(this)
        return START_STICKY
    }

    private fun stopAll() {
        try {
            hev?.stop()
        } catch (_: Exception) { }
        try {
            ss?.stop()
        } catch (_: Exception) { }
        hev = null
        ss = null
        try {
            tun?.close()
        } catch (_: Exception) { }
        tun = null
    }

    private fun startForegroundWithNotification() {
        val ch = NotificationChannel("ipnet", "IPNET VPN", NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val stopPi = PendingIntent.getService(
            this, 1,
            Intent(this, ProxyVpnService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val n = Notification.Builder(this, "ipnet")
            .setContentTitle("IPNET USA active")
            .setContentText("All traffic via USA proxy - tap Stop to disconnect")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentIntent(pi)
            .addAction(android.R.drawable.ic_lock_power_off, "إيقاف", stopPi)
            .build()
        startForeground(1, n)
    }

    override fun onDestroy() {
        scope.cancel()
        stopAll()
        EndpointWorker.cancel(this)
        super.onDestroy()
    }
}
