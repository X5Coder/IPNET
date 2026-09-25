package com.ipnet.android

import android.content.Context
import java.security.SecureRandom

/**
 * Uploads the server bundle (same files x5proxy.py uploads on PC) to the
 * user's own repo after OAuth login, then dispatches the workflow.
 *
 * Assets live in app/src/main/assets/bundle/ (copied from repo root):
 *  server.py, singbox-server.json, proxy.yml, ss-client-template.json,
 *  gitignore.txt (-> .gitignore), README.md (-> README.md).
 * The placeholder X5_Secure_2026!Strong is replaced with a fresh password,
 * exactly like the desktop client does.
 */
object BundleUploader {
    const val PLACEHOLDER = "X5_Secure_2026!Strong"

    private val DEST = mapOf(
        "server.py" to "server.py",
        "singbox-server.json" to "singbox-server.json",
        "proxy.yml" to ".github/workflows/proxy.yml",
        "ss-client-template.json" to "ss-client-template.json",
        "gitignore.txt" to ".gitignore",
        "README.md" to "README.md",
    )

    fun generatePassword(): String {
        val chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!#"
        val rnd = SecureRandom()
        val core = (1..16).map { chars[rnd.nextInt(chars.length)] }.joinToString("")
        return "X5_$core!Strong"
    }

    /** Uploads everything, dispatches the workflow, returns (owner, password). */
    suspend fun uploadAll(context: Context, api: GitHubApi, repo: String, token: String): Pair<String, String> {
        val me = api.username()
        api.ensurePublicRepo(repo)
        // Reuse existing password so a re-run doesn't kill a live endpoint.
        // Fresh API read: proves what is in the repo RIGHT NOW.
        var password = ""
        try {
            val snap = RepoCheck.snapshotSmart(me, repo, api)
            if (snap.password.isNotEmpty()) password = snap.password
        } catch (_: Exception) { }
        if (password.isEmpty()) password = generatePassword()
        val am = context.assets
        for ((asset, dest) in DEST) {
            val raw = am.open("bundle/$asset").bufferedReader().use { it.readText() }
            val content = raw.replace(PLACEHOLDER, password)
            api.putFile(me, repo, dest, content, "ipnet-android: add $dest")
        }
        api.dispatch(me, repo)
        return me to password
    }
}
