package com.ipnet.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import kotlinx.coroutines.*

/**
 * Device-level VPN: TUN interface -> sing-box Shadowsocks (USA via bore).
 *
 *  1. Builder(): address 10.8.0.2/32, route 0.0.0.0/0, DNS 1.1.1.1.
 *  2. LibboxTunnel drives libbox with a tun-in -> ss-out config and
 *     protect()s tunnel sockets so they bypass the TUN (no loop).
 *  3. EndpointWorker (WorkManager, 30 min) re-reads ss_url.txt and
 *     restarts us with the renewed port — mirrors desktop run_terminal.
 */
class ProxyVpnService : VpnService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var tun: ParcelFileDescriptor? = null
    private val tunnel = LibboxTunnel(this)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForegroundWithNotification()
        val host = intent?.getStringExtra("ss_host").orEmpty()
        val port = intent?.getIntExtra("ss_port", 0) ?: 0
        val password = intent?.getStringExtra("ss_password").orEmpty()
        val method = intent?.getStringExtra("ss_method") ?: "aes-256-gcm"
        if (host.isEmpty() || port == 0 || password.isEmpty()) {
            stopSelf()
            return START_NOT_STICKY
        }
        Prefs.save(this, intent?.getStringExtra("owner") ?: Prefs.load(this)["owner"].orEmpty(),
            intent?.getStringExtra("repo") ?: Prefs.load(this)["repo"].orEmpty(),
            host, port, password, method)
        scope.launch {
            try {
                tun?.close()
                tun = Builder()
                    .addAddress("10.8.0.2", 32)
                    .addRoute("0.0.0.0", 0)
                    .addDnsServer("1.1.1.1")
                    .addDnsServer("8.8.8.8")
                    .setSession("IPNET USA")
                    .setBlocking(true)
                    .establish()
                val fd = tun ?: throw RuntimeException("TUN establish failed")
                val cfg = tunnel.buildClientJson(fd.fd, host, port, password, method)
                tunnel.start(cfg, fd)
            } catch (e: Exception) {
                stopSelf()
            }
        }
        EndpointWorker.schedule(this)
        return START_STICKY
    }

    private fun startForegroundWithNotification() {
        val ch = NotificationChannel("ipnet", "IPNET VPN", NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val n = Notification.Builder(this, "ipnet")
            .setContentTitle("IPNET USA active")
            .setContentText("All traffic via USA proxy")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentIntent(pi)
            .build()
        startForeground(1, n)
    }

    override fun onDestroy() {
        scope.cancel()
        tunnel.close()
        tun?.close()
        EndpointWorker.cancel(this)
        super.onDestroy()
    }
}
