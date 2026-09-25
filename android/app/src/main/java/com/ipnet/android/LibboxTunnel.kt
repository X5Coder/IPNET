package com.ipnet.android

import android.net.VpnService
import android.os.ParcelFileDescriptor
import org.json.JSONObject

/**
 * Data-plane bridge to sing-box (JitPack: com.github.singbox-android:libbox).
 *
 * Canonical gomobile usage:
 *   val svc = Libbox.newService(clientJson, platform)
 *   svc.start() ... svc.close()
 * where `platform` implements libbox.PlatformInterface and its protect(fd)
 * delegates to VpnService.protect() so tunnel sockets bypass the TUN
 * (otherwise traffic loops back into the VPN and dies).
 *
 * NOTE: if the first Gradle sync reports a renamed libbox method, the fix
 * is confined to this single file (it mirrors the pinned 1.14.0 API).
 */
class LibboxTunnel(private val vpn: VpnService) {

    private var boxService: Any? = null

    /** sing-box client config: TUN in -> Shadowsocks out (USA via bore). */
    fun buildClientJson(
        tunFd: Int, host: String, port: Int, password: String, method: String,
    ): String = JSONObject()
        .put("log", JSONObject().put("level", "warning"))
        .put("inbounds", org.json.JSONArray().put(
            JSONObject()
                .put("type", "tun").put("tag", "tun-in")
                .put("interface_name", "ipnet0")
                .put("inet4_address", "10.8.0.2/32")
                .put("mtu", 9000).put("stack", "system")
                .put("auto_route", false) // routes come from VpnService.Builder
        ))
        .put("outbounds", org.json.JSONArray().put(
            JSONObject()
                .put("type", "shadowsocks").put("tag", "usa-out")
                .put("server", host).put("server_port", port)
                .put("method", method).put("password", password)
        ))
        .put("route", JSONObject().put("final", "usa-out"))
        .toString()

    fun start(configJson: String, tun: ParcelFileDescriptor) {
        close()
        try {
            val libbox = Class.forName("libbox.Libbox")
            val newService = libbox.methods.first { it.name == "newService" }
            // Platform bridge: only protect() is load-bearing for us; extra
            // interface methods (if any on this libbox version) get defaults
            // via Proxy below. Compile errors here pinpoint renames exactly.
            val platformProxy = java.lang.reflect.Proxy.newProxyInstance(
                vpn.classLoader,
                arrayOf(Class.forName("libbox.PlatformInterface")),
            ) { _, method, args ->
                when (method.name) {
                    "protect" -> vpn.protect((args?.get(0) as Number).toInt())
                    "getMTU" -> 9000
                    "getTUN" -> tun.fd
                    else -> defaultFor(method.returnType)
                }
            }
            boxService = newService.invoke(null, configJson, platformProxy)
            boxService!!.javaClass.getMethod("start").invoke(boxService)
        } catch (e: Exception) {
            throw RuntimeException("sing-box start failed: ${e.message}", e)
        }
    }

    fun close() {
        try {
            boxService?.javaClass?.getMethod("close")?.invoke(boxService)
        } catch (_: Exception) { }
        boxService = null
    }

    private fun defaultFor(t: Class<*>): Any? = when (t) {
        Boolean::class.javaPrimitiveType -> false
        Int::class.javaPrimitiveType -> 0
        Long::class.javaPrimitiveType -> 0L
        else -> null
    }
}
