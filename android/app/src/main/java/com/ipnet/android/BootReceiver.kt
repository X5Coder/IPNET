package com.ipnet.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Best-effort VPN restart after reboot when a config was saved.
 * The consent (VpnService.prepare) survives reboots, so no dialog needed.
 * The OS-guaranteed path is the system "Always-on VPN" toggle, which the
 * app opens from its setup screen; this receiver covers the rest.
 * Wrapped in try/catch: on newest Android an FGS start from background
 * may be refused, in which case Always-on remains the fallback.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val cfg = Prefs.load(context)
        val host = cfg["host"].orEmpty()
        val port = cfg["port"]?.toIntOrNull() ?: 0
        val password = cfg["password"].orEmpty()
        if (host.isEmpty() || port == 0 || password.isEmpty()) return
        try {
            val i = Intent(context, ProxyVpnService::class.java).apply {
                putExtra("owner", cfg["owner"].orEmpty())
                putExtra("repo", cfg["repo"].orEmpty())
                putExtra("ss_host", host)
                putExtra("ss_port", port)
                putExtra("ss_password", password)
                putExtra("ss_method", cfg["method"].orEmpty().ifEmpty { "aes-256-gcm" })
            }
            context.startForegroundService(i)
        } catch (_: Exception) { }
    }
}
