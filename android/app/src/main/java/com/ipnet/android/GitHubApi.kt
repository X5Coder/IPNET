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
