package com.ipnet.android

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * Flow (same idea as x5proxy.py, latest SDK):
 *  1. Paste repo link (owner/repo or full URL).
 *  2. [فحص وتشغيل] -> RepoCheck.snapshot via raw, no login.
 *     - has code + password + endpoint -> save + [تشغيل VPN] active.
 *     - has code but no endpoint yet -> save, waiting message.
 *     - empty/private -> ask OAuth login, then upload code + dispatch.
 *  3. [تشغيل VPN] -> VpnService.prepare() consent -> ProxyVpnService
 *     routes the whole device through the USA endpoint.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var repoInput: EditText
    private lateinit var status: TextView
    private var pendingEndpoint: Triple<String, Int, Pair<String, String>>? = null
    private var pendingOwner: String = ""
    private var pendingRepo: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }
        repoInput = EditText(this).apply { hint = "owner/repo or github.com link" }
        val checkBtn = Button(this).apply { text = "فحص وتشغيل" }
        val vpnBtn = Button(this).apply { text = "تشغيل VPN"; isEnabled = false }
        val loginBtn = Button(this).apply { text = "تسجيل GitHub (OAuth)"; isEnabled = false }
        status = TextView(this)
        layout.addView(repoInput); layout.addView(checkBtn)
        layout.addView(loginBtn); layout.addView(vpnBtn); layout.addView(status)
        setContentView(layout)

        checkBtn.setOnClickListener { checkRepo { vpnBtn.isEnabled = it; loginBtn.isEnabled = !it } }
        loginBtn.setOnClickListener { oauthThenUpload() }
        vpnBtn.setOnClickListener { startVpn() }
    }

    private fun checkRepo(onDone: (vpnReady: Boolean) -> Unit) {
        val parsed = RepoCheck.parseRepoUrl(repoInput.text.toString())
        if (parsed == null) {
            status.text = "الرابط غلط. مثال: SOMEONE/my-proxy"
            onDone(false); return
        }
        val (owner, repo) = parsed
        pendingOwner = owner; pendingRepo = repo
        status.text = "بفحص $owner/$repo ..."
        lifecycleScope.launch {
            try {
                val snap = RepoCheck.snapshot(owner, repo)
                if (!snap.hasCode) {
                    status.text = "فاضي: سجل دخول وارفع الكود."
                    onDone(false); return@launch
                }
                if (snap.password.isEmpty()) {
                    status.text = "فيه كود بس الباسورد مش مقروء."
                    onDone(false); return@launch
                }
                if (snap.endpoint.isEmpty()) {
                    status.text = "الكود موجود بس السيرفر لسه بيبني. استنى دقايق ودوس فحص تاني."
                    onDone(false); return@launch
                }
                val (h, p) = snap.endpoint.split(":")
                pendingEndpoint = Triple(h, p.toInt(), snap.password to snap.method)
                Prefs.save(this@MainActivity, owner, repo, h, p.toInt(), snap.password, snap.method)
                status.text = "تمام! endpoint: ${snap.endpoint} — دوس تشغيل VPN."
                onDone(true)
            } catch (e: Exception) {
                status.text = "فشل الفحص: ${e.message}"
                onDone(false)
            }
        }
    }

    private fun oauthThenUpload() {
        status.text = "بيفتح github.com/device ..."
        lifecycleScope.launch {
            try {
                val dev = AuthManager.requestDeviceCode()
                status.text = "دخل الكود ${dev.userCode} في المتصفح..."
                AuthManager.openAuthorize(this@MainActivity, dev.verificationUri)
                val token = AuthManager.pollToken(dev.deviceCode, dev.intervalSec)
                val api = GitHubApi(token)
                status.text = "بيرفع الكود لـ $pendingRepo ..."
                val (me, _) = BundleUploader.uploadAll(this@MainActivity, api, pendingRepo)
                status.text = "اترفع لـ $me/$pendingRepo واشتغل. استنى endpoint ودوس فحص تاني."
            } catch (e: Exception) {
                status.text = "فشل: ${e.message}"
            }
        }
    }

    private fun startVpn() {
        val ep = pendingEndpoint ?: return
        val intent = VpnService.prepare(this)
        if (intent != null) {
            startActivityForResult(intent, 100)
            return
        }
        launchVpn(ep)
    }

    private fun launchVpn(ep: Triple<String, Int, Pair<String, String>>) {
        val i = Intent(this, ProxyVpnService::class.java).apply {
            putExtra("owner", pendingOwner)
            putExtra("repo", pendingRepo)
            putExtra("ss_host", ep.first)
            putExtra("ss_port", ep.second)
            putExtra("ss_password", ep.third.first)
            putExtra("ss_method", ep.third.second)
        }
        startForegroundService(i)
        status.text = "VPN شغال — كل طلبات الجهاز طالعة أمريكي."
    }

    @Deprecated("legacy")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 100 && resultCode == Activity.RESULT_OK) {
            pendingEndpoint?.let { launchVpn(it) }
        }
    }
}
