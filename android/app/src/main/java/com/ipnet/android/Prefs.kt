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

    fun saveLastRepo(ctx: Context, repo: String) {
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE).edit()
            .putString("last_repo", repo).apply()
    }

    fun loadLastRepo(ctx: Context): String =
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
            .getString("last_repo", "").orEmpty()

    fun saveError(ctx: Context, msg: String) {
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE).edit()
            .putString("last_error", msg).apply()
    }

    fun loadError(ctx: Context): String =
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
            .getString("last_error", "").orEmpty()

    fun clearError(ctx: Context) = saveError(ctx, "")

    /** Step-by-step startup trace (survives death, shown in diagnostics). */
    fun trace(ctx: Context, step: String) {
        val p = ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
        val old = p.getString("trace", "").orEmpty()
        val line = "${android.text.format.DateFormat.format("HH:mm:ss", System.currentTimeMillis())} $step"
        val combined = (old + "\n" + line).split("\n").takeLast(25).joinToString("\n")
        p.edit().putString("trace", combined).apply()
    }

    fun loadTrace(ctx: Context): String =
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE)
            .getString("trace", "").orEmpty()

    fun clearTrace(ctx: Context) {
        ctx.getSharedPreferences(F, Context.MODE_PRIVATE).edit()
            .putString("trace", "").apply()
    }
}
