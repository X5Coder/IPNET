package com.ipnet.android

import android.content.Context

/** Persisted proxy config (same fields as desktop config.json). */
object Prefs {
    private const val F = "ipnet"

    fun save(
        ctx: Context, owner: String, repo: String,
        host: String, port: Int, password: String, method: String,
    ) {
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE).edit()
            .putString("owner", owner).putString("repo", repo)
            .putString("host", host).putInt("port", port)
            .putString("password", password).putString("method", method)
            .apply()
    }

    fun load(ctx: Context): Map<String, String> {
        val p = ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
        return mapOf(
            "owner" to (p.getString("owner", "") ?: ""),
            "repo" to (p.getString("repo", "") ?: ""),
            "host" to (p.getString("host", "") ?: ""),
            "port" to p.getInt("port", 0).toString(),
            "password" to (p.getString("password", "") ?: ""),
            "method" to (p.getString("method", "aes-256-gcm") ?: "aes-256-gcm"),
        )
    }

    fun saveToken(ctx: Context, token: String) {
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE).edit()
            .putString("gh_token", token).apply()
    }

    fun loadToken(ctx: Context): String =
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
            .getString("gh_token", "").orEmpty()
}
