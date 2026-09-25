package com.ipnet.android

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * Android port of x5proxy.py attach logic:
 * parse link -> raw fetch ss_url.txt + password -> attach or fallback upload.
 */
object RepoCheck {
    private val http = OkHttpClient()
    private const val RAW = "https://raw.githubusercontent.com"

    data class Snapshot(
        val hasCode: Boolean,
        val endpoint: String,
        val password: String,
        val method: String,
    )

    fun parseRepoUrl(s: String): Pair<String, String>? {
        val t = s.trim().trim('"').trim('\'')
        Regex("""https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$""")
            .matchEntire(t)?.let { return it.groupValues[1] to it.groupValues[2] }
        Regex("""([^/\s]+)/([^/\s]+?)(?:\.git)?$""")
            .matchEntire(t)?.let { if ("/" in t) return it.groupValues[1] to it.groupValues[2] }
        return null
    }

    private suspend fun raw(url: String): String = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url(url).build()
            http.newCall(req).execute().use { r ->
                if (!r.isSuccessful) return@withContext ""
                r.body?.string().orEmpty().trim()
            }
        } catch (_: Exception) { "" }
    }

    private fun extractPassword(singbox: String, workflow: String): Pair<String, String> {
        if (singbox.isNotEmpty()) {
            try {
                val inb = JSONObject(singbox).getJSONArray("inbounds").getJSONObject(0)
                val p = inb.optString("password", "")
                if (p.isNotEmpty()) return p to inb.optString("method", "aes-256-gcm")
            } catch (_: Exception) { }
            Regex(""""password"\s*:\s*"([^"]{4,128})"""").find(singbox)?.let {
                return it.groupValues[1] to "aes-256-gcm"
            }
        }
        Regex("""PROXY_PASS='([^']{4,128})'""").find(workflow)?.let {
            return it.groupValues[1] to "aes-256-gcm"
        }
        return "" to "aes-256-gcm"
    }

    suspend fun snapshot(owner: String, repo: String): Snapshot {
        val base = "$RAW/$owner/$repo/main"
        val ss = raw("$base/ss_url.txt")
        val bore = raw("$base/bore_url.txt")
        val endpoint = when {
            Regex("""bore\.pub:\d+""").matches(ss) -> ss
            Regex("""bore\.pub:\d+""").matches(bore) -> bore
            else -> ""
        }
        val singbox = raw("$base/singbox-server.json")
        val workflow = raw("$base/.github/workflows/proxy.yml")
        var hasCode = singbox.isNotEmpty() || workflow.isNotEmpty()
        if (!hasCode) {
            val srv = raw("$base/server.py")
            hasCode = srv.contains("proxy", ignoreCase = true)
        }
        val (pwd, method) = extractPassword(singbox, workflow)
        return Snapshot(hasCode, endpoint, pwd, method)
    }
}
