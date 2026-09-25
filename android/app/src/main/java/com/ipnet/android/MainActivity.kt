package com.ipnet.android

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * IPNET Android — token gate first, everything else after.
 *
 *  0. Token screen ONLY: paste classic token -> validated (identity +
 *     repo+workflow scopes) -> unlocks the rest. Wrong scope/type is
 *     rejected here with an explanation, never later as a cryptic 404.
 *     [تغيير التوكن] goes back to this screen any time.
 *  1. Repo screen: fresh API check (no stale cache) proves whether code
 *     exists RIGHT NOW -> attach, wait, or upload.
 *  2. VPN screen: device TUN + auto-refresh + boot/always-on.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var tokenSection: LinearLayout
    private lateinit var mainSection: LinearLayout
    private lateinit var repoInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var status: TextView
    private lateinit var tokenStatus: TextView
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

        tokenSection = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        tokenSection.addView(title("التوكن أولاً (مرة واحدة)", 14f, true))
        tokenSection.addView(title(
            "من المتصفح: github.com/settings/tokens ← Generate new token (classic) ← علّم الاختيارات اللي تحت زي الصورة بالظبط ← انسخ التوكن والصقه هنا.",
            11f, false, MUTED))
        tokenSection.addView(scopesCard())
        tokenInput = field("ghp_...", true)
        tokenSection.addView(tokenInput)
        tokenSection.addView(action("تحقق ودخول") { saveToken() })
        tokenStatus = title("", 12f, false, "#9F2F2D")
        tokenSection.addView(tokenStatus)
        layout.addView(tokenSection)

        mainSection = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        mainSection.addView(action("← تغيير التوكن") { showTokenScreen() })
        mainSection.addView(title("المستودع", 14f, true))
        mainSection.addView(title("مثال: SOMEONE/my-proxy", 11f, false, MUTED))
        repoInput = field("owner/repo أو رابط كامل", false)
        mainSection.addView(repoInput)
        mainSection.addView(action("فحص وتشغيل") { checkRepo() })
        uploadBtn = action("رفع الكود وتشغيل") { uploadThenWait() }
        uploadBtn.visibility = View.GONE
        mainSection.addView(uploadBtn)
        vpnBtn = action("تشغيل VPN") { startVpn() }
        vpnBtn.visibility = View.GONE
        mainSection.addView(vpnBtn)
        status = title("", 12f, false, "#9F2F2D")
        mainSection.addView(status)
        mainSection.addView(divider())
        mainSection.addView(title("يفضل شغال", 14f, true))
        mainSection.addView(action("تجاهل تحسين البطارية") { askIgnoreBattery() })
        mainSection.addView(action("تثبيت VPN دائم") { openVpnSettings() })
        mainSection.addView(title(
            "من إعدادات VPN فعّل Always-on على IPNET — النظام نفسه يرجع الخدمة بعد إعادة التشغيل.",
            11f, false, MUTED))
        layout.addView(mainSection)

        setContentView(root)

        // Silent re-validation of a saved token: valid -> straight to main.
        val saved = Prefs.loadToken(this)
        if (saved.isNotEmpty()) {
            tokenStatus.text = "بتحقق من التوكن المحفوظ ..."
            lifecycleScope.launch {
                try {
                    val api = GitHubApi(saved)
                    api.username()
                    checkScopesOrThrow(api)
                    showMainScreen()
                } catch (e: Exception) {
                    tokenStatus.text = "التوكن المحفوظ مرفوض: ${e.message} — الصق واحد جديد."
                }
            }
        }
    }

    /** Dark scopes card replicating the classic-token checkboxes image. */
    private fun scopesCard(): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(10), dp(14), dp(10))
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#111827"))
                cornerRadius = dp(12).toFloat()
            }
        }
        card.addView(scopeCheck("repo", 0))
        card.addView(scopeCheck("repo:status", 1))
        card.addView(scopeCheck("repo_deployment", 1))
        card.addView(scopeCheck("public_repo", 1))
        card.addView(scopeCheck("repo:invite", 1))
        card.addView(scopeCheck("security_events", 1))
        card.addView(scopeCheck("workflow", 0))
        val hint = TextView(this).apply {
            text = "علّم نفس الاختيارات دي بالظبط."
            setTextColor(Color.parseColor("#9CA3AF"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
            setPadding(0, dp(6), 0, 0)
        }
        card.addView(hint)
        val lp = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT)
        lp.setMargins(0, dp(8), 0, dp(8))
        card.layoutParams = lp
        return card
    }

    private fun scopeCheck(t: String, indent: Int): CheckBox =
        CheckBox(this).apply {
            text = t
            isChecked = true
            isEnabled = false // illustration only: this is what YOU tick on GitHub
            setTextColor(Color.WHITE)
            buttonTintList = android.content.res.ColorStateList.valueOf(
                Color.parseColor("#22C55E"))
            setPadding(dp(8 + indent * 18), dp(2), dp(8), dp(2))
        }

    // ---------- UI helpers ----------
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

    private fun showMainScreen() {
        tokenSection.visibility = View.GONE
        mainSection.visibility = View.VISIBLE
    }

    private fun showTokenScreen() {
        mainSection.visibility = View.GONE
        tokenSection.visibility = View.VISIBLE
        tokenStatus.text = ""
    }

    // ---------- 0. token gate ----------
    private suspend fun checkScopesOrThrow(api: GitHubApi) {
        val scopes = api.scopes()
        if (scopes.isEmpty()) {
            throw RuntimeException(
                "التوكن fine-grained — مبيعرفش ينشئ مستودعات. اعمل classic وعلّم repo و workflow.")
        }
        val missing = listOf("repo", "workflow").filter { it !in scopes }
        if (missing.isNotEmpty()) {
            throw RuntimeException("ناقص صلاحيات: ${missing.joinToString()} — علّم repo و workflow.")
        }
    }

    private fun apiOrNull(): GitHubApi? {
        val t = Prefs.loadToken(this)
        return if (t.isEmpty()) null else GitHubApi(t)
    }

    private fun saveToken() {
        val t = tokenInput.text.toString().trim()
        if (t.isEmpty() || t.startsWith("•")) {
            tokenStatus.text = "الصق التوكن الأول."
            return
        }
        tokenStatus.text = "بتحقق ..."
        lifecycleScope.launch {
            try {
                val api = GitHubApi(t)
                val me = api.username()
                checkScopesOrThrow(api)
                Prefs.saveToken(this@MainActivity, t)
                showMainScreen()
                status.text = "مسجل كـ $me ✓"
            } catch (e: Exception) {
                tokenStatus.text = "مرفوض: ${e.message}"
            }
        }
    }

    // ---------- 1. fresh check / upload (Contents API, no stale cache) ----------
    private fun checkRepo() {
        val parsed = RepoCheck.parseRepoUrl(repoInput.text.toString())
        if (parsed == null) {
            status.text = "الرابط غلط. مثال: SOMEONE/my-proxy"
            return
        }
        val (owner, repo) = parsed
        pendingOwner = owner
        pendingRepo = repo
        uploadBtn.visibility = View.GONE
        vpnBtn.visibility = View.GONE
        status.text = "بفحص $owner/$repo من السيرفر مباشرة ..."
        lifecycleScope.launch {
            try {
                val snap = RepoCheck.snapshotSmart(owner, repo, apiOrNull())
                if (!snap.hasCode) {
                    status.text = "المستودع فاضي فعلاً (فحص مباشر) — دوس رفع الكود وتشغيل."
                    uploadBtn.visibility = View.VISIBLE
                    return@launch
                }
                if (snap.password.isEmpty()) {
                    status.text = "فيه ملفات بس الباسورد مش مقروء — ارفع الكود من جديد."
                    uploadBtn.visibility = View.VISIBLE
                    return@launch
                }
                if (snap.endpoint.isEmpty()) {
                    status.text = "الكود موجود فعلاً بس السيرفر لسه بيبني — استنى دقايق ودوس فحص تاني."
                    return@launch
                }
                gotEndpoint(snap.endpoint, snap.password, snap.method)
            } catch (e: Exception) {
                status.text = "فشل الفحص: ${e.message}"
            }
        }
    }

    private fun gotEndpoint(endpoint: String, password: String, method: String) {
        val (h, p) = endpoint.split(":")
        pendingEndpoint = Triple(h, p.toInt(), password to method)
        Prefs.save(this, pendingOwner, pendingRepo, h, p.toInt(), password, method)
        status.text = "تمام! endpoint: $endpoint — دوس تشغيل VPN."
        vpnBtn.visibility = View.VISIBLE
    }

    private fun uploadThenWait() {
        val token = Prefs.loadToken(this)
        if (token.isEmpty()) {
            status.text = "احفظ التوكن الأول."
            return
        }
        status.text = "بيرفع الكود لـ $pendingRepo ..."
        lifecycleScope.launch {
            try {
                val (me, _) = BundleUploader.uploadAll(
                    this@MainActivity, GitHubApi(token), pendingRepo, token)
                pendingOwner = me
                status.text = "اترفع لـ $me/$pendingRepo واشتغل — استنى دقايق ودوس فحص."
            } catch (e: Exception) {
                status.text = "فشل الرفع: ${e.message}"
            }
        }
    }

    // ---------- 2. VPN + staying alive ----------
    private fun startVpn() {
        val ep = pendingEndpoint ?: run {
            val c = Prefs.load(this)
            val h = c["host"].orEmpty()
            val p = c["port"]?.toIntOrNull() ?: 0
            val pw = c["password"].orEmpty()
            if (h.isEmpty() || p == 0 || pw.isEmpty()) {
                status.text = "مفيش endpoint محفوظ — اعمل فحص الأول."
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
        status.text = "VPN شغال — كل طلبات الجهاز طالعة أمريكي. الإيقاف من الإشعار."
    }

    private fun askIgnoreBattery() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            status.text = "تحسين البطارية متجاهل أصلاً ✓"
            return
        }
        try {
            startActivity(Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            status.text = "افتحها يدوياً من إعدادات البطارية."
        }
    }

    private fun openVpnSettings() {
        try {
            startActivity(Intent("android.net.vpn.SETTINGS"))
            status.text = "فعّل Always-on على IPNET من القائمة."
        } catch (e: Exception) {
            status.text = "افتح إعدادات VPN يدوياً وفعّل Always-on."
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
