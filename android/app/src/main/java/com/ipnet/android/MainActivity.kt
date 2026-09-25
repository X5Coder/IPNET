package com.ipnet.android

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.util.TypedValue
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * IPNET Android — same idea as the desktop client, phone styling to match:
 * warm white (#FBFBFA), off-black type, hairline dividers, one solid CTA.
 *
 * Flow:
 *  1. Paste a GitHub token once (classic token, scopes: repo + workflow).
 *     Created at github.com/settings/tokens — no OAuth app, no client_id,
 *     nothing to misconfigure (this replaces the device-code flow).
 *  2. Paste repo link -> [فحص]: working code attaches directly, empty repo
 *     shows [رفع الكود وتشغيل] (uploads bundle + dispatches, like the PC).
 *  3. [تشغيل VPN]: system consent once, then device-level TUN stays up
 *     with a Stop action in its notification + auto-restart after reboot
 *     (BootReceiver) + optional system Always-on toggle.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var repoInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var status: TextView
    private lateinit var uploadBtn: Button
    private lateinit var vpnBtn: Button
    private var pendingEndpoint: Triple<String, Int, Pair<String, String>>? = null
    private var pendingOwner: String = ""
    private var pendingRepo: String = ""

    private val INK = "#111111"
    private val MUTED = "#787774"
    private val HAIR = "#EAEAEA"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = ScrollView(this).apply { setBackgroundColor(Color.parseColor("#FBFBFA")) }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(20), dp(24), dp(32))
        }
        root.addView(layout)

        layout.addView(title("IPNET", 22f, true))
        layout.addView(title("USA proxy in one click.", 13f, false, MUTED))
        layout.addView(divider())

        layout.addView(title("١ — توكن GitHub (مرة واحدة)", 14f, true))
        layout.addView(title(
            "github.com/settings/tokens ← Generate new token (classic) ← علّم repo و workflow والصقه هنا.",
            11f, false, MUTED))
        tokenInput = field("ghp_...", true)
        if (Prefs.loadToken(this).isNotEmpty()) tokenInput.setText("•••••• محفوظ ✓")
        layout.addView(tokenInput)
        layout.addView(action("حفظ التوكن") { saveToken() })
        layout.addView(divider())

        layout.addView(title("٢ — رابط المستودع", 14f, true))
        layout.addView(title("مثال: SOMEONE/my-proxy", 11f, false, MUTED))
        repoInput = field("owner/repo أو رابط كامل", false)
        layout.addView(repoInput)
        layout.addView(action("فحص وتشغيل") { checkRepo() })
        uploadBtn = action("رفع الكود وتشغيل") { uploadThenWait() }
        uploadBtn.visibility = View.GONE
        layout.addView(uploadBtn)
        vpnBtn = action("تشغيل VPN") { startVpn() }
        vpnBtn.visibility = View.GONE
        layout.addView(vpnBtn)
        status = title("", 12f, false, "#9F2F2D")
        layout.addView(status)
        layout.addView(divider())

        layout.addView(title("٣ — يفضل شغال", 14f, true))
        layout.addView(action("تجاهل تحسين البطارية") { askIgnoreBattery() })
        layout.addView(action("تثبيت VPN دائم") { openVpnSettings() })
        layout.addView(title(
            "من إعدادات VPN فعّل Always-on على IPNET — النظام نفسه يرجع الخدمة بعد إعادة التشغيل.",
            11f, false, MUTED))
        setContentView(root)
    }

    // ---------- UI helpers (IPNET look) ----------
    private fun dp(n: Int) = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, n.toFloat(), resources.displayMetrics).toInt()

    private fun title(t: String, sp: Float, bold: Boolean, color: String = INK): TextView =
        TextView(this).apply {
            text = t
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sp)
            setTextColor(Color.parseColor(color))
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, dp(4), 0, dp(4))
        }

    private fun divider(): View = View(this).apply {
        setBackgroundColor(Color.parseColor(HAIR))
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(1)).apply {
            setMargins(0, dp(10), 0, dp(10))
        }
    }

    private fun field(hint: String, password: Boolean): EditText =
        EditText(this).apply {
            this.hint = hint
            if (password) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = GradientDrawable().apply {
                setColor(Color.WHITE)
                setStroke(dp(1), Color.parseColor(HAIR))
                cornerRadius = dp(10).toFloat()
            }
        }

    private fun action(t: String, onClick: () -> Unit): Button =
        Button(this).apply {
            text = t
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                setColor(Color.parseColor(INK))
                cornerRadius = dp(14).toFloat()
            }
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(50)).apply {
                setMargins(0, dp(6), 0, dp(6))
            }
        }

    private fun say(t: String) {
        status.text = t
    }

    // ---------- 1. token ----------
    private fun saveToken() {
        var t = tokenInput.text.toString().trim()
        if (t.startsWith("•")) t = Prefs.loadToken(this)
        if (t.isEmpty()) {
            say("الصق التوكن الأول.")
            return
        }
        say("بتحقق من التوكن ...")
        lifecycleScope.launch {
            try {
                val me = GitHubApi(t).username()
                Prefs.saveToken(this@MainActivity, t)
                tokenInput.setText("•••••• محفوظ ✓")
                say("تمام! مسجل كـ $me.")
            } catch (e: Exception) {
                say("التوكن مرفوض: ${e.message}")
            }
        }
    }

    // ---------- 2. check / upload ----------
    private fun checkRepo() {
        val parsed = RepoCheck.parseRepoUrl(repoInput.text.toString())
        if (parsed == null) {
            say("الرابط غلط. مثال: SOMEONE/my-proxy")
            return
        }
        val (owner, repo) = parsed
        pendingOwner = owner
        pendingRepo = repo
        uploadBtn.visibility = View.GONE
        vpnBtn.visibility = View.GONE
        say("بفحص $owner/$repo ...")
        lifecycleScope.launch {
            try {
                val snap = RepoCheck.snapshot(owner, repo)
                if (!snap.hasCode) {
                    if (Prefs.loadToken(this@MainActivity).isEmpty()) {
                        say("المستودع فاضي — احفظ التوكن الأول عشان أرفع الكود.")
                    } else {
                        say("المستودع فاضي — دوس رفع الكود وتشغيل.")
                        uploadBtn.visibility = View.VISIBLE
                    }
                    return@launch
                }
                if (snap.password.isEmpty()) {
                    say("فيه كود بس الباسورد مش مقروء.")
                    return@launch
                }
                if (snap.endpoint.isEmpty()) {
                    say("الكود موجود بس السيرفر لسه بيبني — استنى دقايق ودوس فحص تاني.")
                    return@launch
                }
                gotEndpoint(snap.endpoint, snap.password, snap.method)
            } catch (e: Exception) {
                say("فشل الفحص: ${e.message}")
            }
        }
    }

    private fun gotEndpoint(endpoint: String, password: String, method: String) {
        val (h, p) = endpoint.split(":")
        pendingEndpoint = Triple(h, p.toInt(), password to method)
        Prefs.save(this, pendingOwner, pendingRepo, h, p.toInt(), password, method)
        say("تمام! endpoint: $endpoint — دوس تشغيل VPN.")
        vpnBtn.visibility = View.VISIBLE
    }

    private fun uploadThenWait() {
        val token = Prefs.loadToken(this)
        if (token.isEmpty()) {
            say("احفظ التوكن الأول.")
            return
        }
        say("بيرفع الكود لـ $pendingRepo ...")
        lifecycleScope.launch {
            try {
                val (me, _) = BundleUploader.uploadAll(
                    this@MainActivity, GitHubApi(token), pendingRepo)
                pendingOwner = me
                say("اترفع لـ $me/$pendingRepo واشتغل — استنى دقايق ودوس فحص.")
            } catch (e: Exception) {
                say("فشل الرفع: ${e.message}")
            }
        }
    }

    // ---------- 3. VPN + staying alive ----------
    private fun startVpn() {
        val ep = pendingEndpoint ?: run {
            // Reboot case: rebuild from saved prefs.
            val c = Prefs.load(this)
            val h = c["host"].orEmpty()
            val p = c["port"]?.toIntOrNull() ?: 0
            val pw = c["password"].orEmpty()
            if (h.isEmpty() || p == 0 || pw.isEmpty()) {
                say("مفيش endpoint محفوظ — اعمل فحص الأول.")
                return
            }
            pendingOwner = c["owner"].orEmpty()
            pendingRepo = c["repo"].orEmpty()
            Triple(h, p, pw to (c["method"].orEmpty().ifEmpty { "aes-256-gcm" }))
        }
        val intent = VpnService.prepare(this)
        if (intent != null) {
            startActivityForResult(intent, 100)
            pendingEndpoint = ep
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
        say("VPN شغال — كل طلبات الجهاز طالعة أمريكي. الإيقاف من الإشعار.")
    }

    private fun askIgnoreBattery() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            say("تحسين البطارية متجاهل أصلاً ✓")
            return
        }
        try {
            startActivity(Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            say("افتحها يدوياً من إعدادات البطارية.")
        }
    }

    private fun openVpnSettings() {
        try {
            startActivity(Intent("android.net.vpn.SETTINGS"))
            say("فعّل Always-on على IPNET من القائمة.")
        } catch (e: Exception) {
            say("افتح إعدادات VPN يدوياً وفعّل Always-on.")
        }
    }

    @Deprecated("legacy")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 100 && resultCode == Activity.RESULT_OK) {
            pendingEndpoint?.let { launchVpn(it) }
        }
    }
}
