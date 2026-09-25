package com.ipnet.android

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.Base64

/**
 * Minimal GitHub REST wrapper: create repo, upload files, dispatch workflow.
 * Mirrors x5proxy.py setup_backend() owned-copy path.
 */
class GitHubApi(private val token: String) {
    private val http = OkHttpClient()
    private val json = "application/json".toMediaType()

    private suspend fun call(method: String, url: String, body: String? = null): Pair<Int, String> =
        withContext(Dispatchers.IO) {
            val b = Request.Builder().url(url)
                .header("Accept", "application/vnd.github+json")
                .header("Authorization", "Bearer $token")
                .header("X-GitHub-Api-Version", "2022-11-28")
            when (method) {
                "GET" -> b.get()
                "POST" -> b.post((body ?: "").toRequestBody(json))
                "PUT" -> b.put((body ?: "").toRequestBody(json))
            }
            http.newCall(b.build()).execute().use { r ->
                r.code to (r.body?.string().orEmpty())
            }
        }

    suspend fun username(): String {
        val (code, body) = call("GET", "https://api.github.com/user")
        if (code != 200) throw RuntimeException("user HTTP $code")
        return JSONObject(body).getString("login")
    }

    /** Classic-token scopes from the X-OAuth-Scopes header (empty for fine-grained). */
    suspend fun scopes(): Set<String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("https://api.github.com/user")
            .header("Accept", "application/vnd.github+json")
            .header("Authorization", "Bearer $token")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .get().build()
        http.newCall(req).execute().use { r ->
            if (r.code != 200) throw RuntimeException("user HTTP ${r.code}")
            r.body?.close()
            r.headers("X-OAuth-Scopes").flatMap { h -> h.split(",") }
                .map { it.trim() }.filter { it.isNotEmpty() }.toSet()
        }
    }

    /**
     * Fresh file content via Contents API (no CDN cache, unlike raw).
     * Returns null ONLY on 404 (truly absent). Throws on 401/403/rate-limit
     * so callers never mistake an auth failure for "empty repo".
     */
    suspend fun getFile(owner: String, repo: String, path: String): String? {
        val (code, body) = call("GET", "https://api.github.com/repos/$owner/$repo/contents/$path?ref=main")
        if (code == 404) return null
        if (code == 403 && body.contains("rate limit", ignoreCase = true)) {
            throw RuntimeException("GitHub rate limit - حاول بعد دقيقة")
        }
        if (code != 200) throw RuntimeException("read $path HTTP $code")
        val content = JSONObject(body).optString("content", "").replace("\n", "")
        if (content.isEmpty()) return null
        return String(Base64.getDecoder().decode(content), Charsets.UTF_8)
    }

    suspend fun ensurePublicRepo(repo: String) {
        val me = username()
        val (code, _) = call("GET", "https://api.github.com/repos/$me/$repo")
        if (code == 200) return
        if (code != 404) throw RuntimeException("repo check HTTP $code")
        val payload = JSONObject()
            .put("name", repo).put("private", false)
            .put("description", "My private USA proxy (IPNET)").toString()
        val (c2, _) = call("POST", "https://api.github.com/user/repos", payload)
        if (c2 != 200 && c2 != 201) throw RuntimeException("create HTTP $c2")
    }

    suspend fun putFile(owner: String, repo: String, path: String, content: String, msg: String) {
        val url = "https://api.github.com/repos/$owner/$repo/contents/$path"
        val (gc, gb) = call("GET", url)
        val sha = if (gc == 200) JSONObject(gb).optString("sha", null) else null
        val payload = JSONObject()
            .put("message", msg)
            .put("content", Base64.getEncoder().encodeToString(content.toByteArray()))
        if (sha != null) payload.put("sha", sha)
        val (code, _) = call("PUT", url, payload.toString())
        if (code != 200 && code != 201) throw RuntimeException("upload $path HTTP $code")
    }

    suspend fun dispatch(owner: String, repo: String) {
        val payload = JSONObject().put("ref", "main").toString()
        call("POST", "https://api.github.com/repos/$owner/$repo/actions/workflows/proxy.yml/dispatches", payload)
    }
}
