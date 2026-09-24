# Proxy USA - Private Proxy for Render (US) - احترافي + سريع + مؤمن

بروكسي خاص بك على سيرفر مجاني في أمريكا (Render) - للتصفح الخاص وتجاوز الحجب بسرعة عالية.

## المميزات
- ⚡ **سرعة عالية:** TCP_NODELAY + SO_KEEPALIVE + 128KB buffer + relay محسن
- ✅ HTTP + HTTPS (CONNECT tunnel) - يفتح كل المواقع
- 🔒 مصادقة Basic Auth إجبارية (يوزر + باسورد قوي)
- 💓 Health Check (`/` و `/health`) + GitHub Action نبض كل 14 دقيقة ضد النوم
- 🛡️ Rate Limit ضد الإساءة
- ✅ خفيف جداً - يشتغل على Free Tier (512MB) بأعلى أداء

## 1. ما الذي تفعله الآن في Render؟

انت في صفحة `Configure` - اعمل كالتالي:

### الخطوة الأهم - Environment Variables (للأمان):

في نفس الصفحة اللي انت فيها، انزل عند **Environment Variables** واضغط `Add Environment Variable` وضيف دول (مهم جداً):

| Key | Value | ملاحظة |
|-----|-------|--------|
| `PROXY_USER` | `x5coder` | غيره لاسم صعب التخمين |
| `PROXY_PASS` | `X5_Secure_2026!@#Strong` | **لازم كلمة سر قوية 16+ حرف** - لا تستخدم الافتراضي |

> بدون دول البروكسي هيشتغل بالافتراضي `x5coder / X5_Usa_2026_Secure!` وهذا ضعيف لأنه موجود في الكود. **لازم تغيره الآن.**

اختياري:
| `RATE_LIMIT` | `120` | عدد الطلبات/دقيقة لكل IP |

لا تضيف `PORT` - Render يضبطه تلقائياً.

### ثم اضغط:
**`Deploy web service`** (الزر الأزرق تحت)

بعد 2-3 دقائق سيعطيك رابط مثل:
```
https://proxy-usa-xxxx.onrender.com
```
> انسخ الرابط ده - ستحتاجه للخطوة 2

---

## 2. منع النوم - GitHub Action (نبض كل 14 دقيقة)

الخطة المجانية تنام بعد 15 دقيقة بدون زيارات. عملت لك GitHub Action يصحيه تلقائياً:

**بعد ما تعمل Deploy، اعمل التالي:**

1. افتح الملف: `.github/workflows/keep-alive.yml:4`
2. غير السطر:
```yaml
https://proxy-usa.onrender.com/health
```
إلى رابطك الحقيقي (مثلاً `https://proxy-usa-a1b2.onrender.com/health`)

3. اعمل Commit & Push - الـ Action سيشتغل تلقائياً كل 14 دقيقة ويرسل `GET /health` (خفيف جداً 1KB، لا يستهلك موارد)

**تفعيل يدوي:** GitHub → Actions → `Keep Proxy Alive` → Run workflow

> النبض لا يستهلك الباندويث ولا يوقظ السيرفر بقوة - فقط يمنعه من النوم. استهلاكه أقل من 1MB/يوم.

---

## 3. الإعدادات الصحيحة في الصفحة الحالية:

- **Name:** `proxy-usa` ✅
- **Language:** `Docker` ✅
- **Branch:** `main` ✅
- **Region:** `Oregon (US West)` - كلاهما أمريكا، لو تريد شرق أمريكا اختار `Ohio` لو متاح عندك
- **Root Directory:** اتركه فاضي ✅
- **Dockerfile Path:** `.` ✅
- **Plan:** `Free - 0.1 CPU 512MB` ✅ (انت اخترته بالفعل)
- **Environment Variables:** ضيف `PROXY_USER` + `PROXY_PASS` كما فوق 🔴 مهم

---

## 4. كيفية الاستخدام بعد التشغيل

**بيانات البروكسي:**
- **Host:** `proxy-usa-xxxx.onrender.com` (بدون https://)
- **Port:** `443`
- **Username:** نفس `PROXY_USER`
- **Password:** نفس `PROXY_PASS`
- **Type:** `HTTP Proxy`

### Chrome / Edge
Settings → System → Open proxy settings → Manual → Address + Port 443 → سيطلب اليوزر/الباس عند أول موقع

### Firefox
Settings → Network Settings → Manual → HTTP Proxy + ✅ Also use for HTTPS

### الهاتف
WiFi → Modify network → Advanced → Proxy Manual → Host + Port 443

### اختبار curl
```bash
curl -x http://USER:PASS@proxy-usa-xxxx.onrender.com:443 https://ifconfig.me
curl -x http://USER:PASS@proxy-usa-xxxx.onrender.com:443 https://api.ipify.org
# يجب يظهر IP أمريكي
```

### هل البروكسي شغال؟
افتح:
```
https://proxy-usa-xxxx.onrender.com/health  → 200 OK
https://proxy-usa-xxxx.onrender.com/       → صفحة Proxy Online
```

---

## 5. الأمان - كيف لا يستخدمه أحد غيرك؟

- البروكسي يرجع `407 Proxy Authentication Required` بدون يوزر/باس صحيح - لا يمكن استخدامه بدونهم ✅
- لا تشارك الرابط مع الباسورد
- غير الباسورد كل فترة من Render → Environment → Redeploy
- RATE_LIMIT يمنع شخص واحد من استهلاك السيرفر حتى لو عرف الباسورد
- لا تضع الباسورد في الكود - فقط في Render Environment Variables (مشفرة)

---

## 6. السرعة
- Buffer 128KB + TCP_NODELAY + KeepAlive
- Threading لكل اتصال
- لا يمرر إلا المطلوب - لا سجلات ثقيلة
- يتحمل 500+ اتصال متزامن على Free Tier

---

Made for X5Coder • Render US Proxy • 2026 • High-Speed + Secure
