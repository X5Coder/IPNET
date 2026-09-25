package com.ipnet.android

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * GitHub login on Android — no gh CLI here.
 *
 * V1 uses OAuth Device Flow (no client_secret in the app):
 *  1. POST https://github.com/login/device/code (client_id only)
 *     -> device_code + user_code + verification_uri
 *  2. App shows user_code, opens verification_uri in Custom Tab.
 *     User clicks Authorize on github.com/device.
 *  3. App polls https://github.com/login/oauth/access_token
 *     (grant_type=device_code) until the token arrives.
 *  4. Token is stored in DataStore (same role as gh auth token on PC).
 *
 * Create one OAuth App at github.com/settings/developers once and put
 * its client_id in BuildConfig / local.properties. No secret needed
 * for device flow.
 */
object AuthManager {
    private const val CLIENT_ID = "REPLACE_WITH_OAUTH_APP_CLIENT_ID"
    private const val DEVICE_CODE_URL = "https://github.com/login/device/code"
    private const val TOKEN_URL = "https://github.com/login/oauth/access_token"

    private val http = OkHttpClient()

    data class DeviceAuth(
        val deviceCode: String,
        val userCode: String,
        val verificationUri: String,
        val intervalSec: Long,
    )

    suspend fun requestDeviceCode(scope: String = "repo workflow"): DeviceAuth =
        withContext(Dispatchers.IO) {
            val body = FormBody.Builder()
                .add("client_id", CLIENT_ID)
                .add("scope", scope)
                .build()
            val req = Request.Builder().url(DEVICE_CODE_URL)
                .post(body).header("Accept", "application/json").build()
            val json = JSONObject(http.newCall(req).execute().body!!.string())
            DeviceAuth(
                deviceCode = json.getString("device_code"),
                userCode = json.getString("user_code"),
                verificationUri = json.optString("verification_uri", "https://github.com/device"),
                intervalSec = json.optLong("interval", 5),
            )
        }

    fun openAuthorize(context: Context, verificationUri: String) {
        CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(verificationUri))
    }

    /** Poll until authorized. Returns token or throws. Call from a coroutine. */
    suspend fun pollToken(deviceCode: String, intervalSec: Long): String {
        while (true) {
            delay(intervalSec * 1000)
            val json = withContext(Dispatchers.IO) {
                val body = FormBody.Builder()
                    .add("client_id", CLIENT_ID)
                    .add("device_code", deviceCode)
                    .add("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
                    .build()
                val req = Request.Builder().url(TOKEN_URL)
                    .post(body).header("Accept", "application/json").build()
                JSONObject(http.newCall(req).execute().body!!.string())
            }
            if (json.has("access_token")) return json.getString("access_token")
            val err = json.optString("error")
            if (err == "authorization_pending" || err == "slow_down") continue
            throw RuntimeException("OAuth failed: $err")
        }
    }

    fun tokenIntent(context: Context): Intent =
        Intent(context, MainActivity::class.java)
}
