# Proxy USA - Private Proxy for Render (US)

بروكسي خاص بك على سيرفر مجاني في أمريكا (Render) - للتصفح الخاص وتجاوز الحجب.

## المميزات
- ✅ HTTP + HTTPS (CONNECT tunnel) - يفتح كل المواقع
- ✅ مصادقة Basic Auth (يوزر + باسورد)
- ✅ Health Check لـ Render (`/` و `/health`)
- ✅ خفيف جداً - يشتغل على Free Tier (512MB)
- ✅ يعمل خلف Render TLS termination

## التثبيت على Render

### 1. ارفع على GitHub
المشروع جاهز في: `https://github.com/X5Coder/proxy-usa`

```bash
git push origin main
```

### 2. في Render Dashboard
1. New → Web Service
2. اختر repo: `X5Coder/proxy-usa`
3. **الإعدادات المهمة:**

| الحقل | القيمة |
|------|--------|
| Name | `proxy-usa` |
| Language | `Docker` |
| Branch | `main` |
| Region | `Ohio (US East)` أو `Oregon (US West)` - كلاهما أمريكا |
| Dockerfile Path | `.` (افتراضي) |
| Plan | `Free - 0.1 CPU 512MB` |

4. **Environment Variables** (مهم للأمان):

| Key | Value |
|-----|-------|
| `PROXY_USER` | اسم المستخدم (مثلاً `x5coder`) |
| `PROXY_PASS` | كلمة السر (قوية، مثلاً `MyS3cure!2026`) |
| `PORT` | يضبط تلقائياً بواسطة Render - لا تغيره |

5. اضغط `Deploy web service`

بعد 2-3 دقائق سيعطيك رابط مثل:
```
https://proxy-usa-xxxx.onrender.com
```

### 3. كيفية الاستخدام

**الرابط هو نفسه الـ Host للبروكسي:**
- **Host:** `proxy-usa-xxxx.onrender.com`
- **Port:** `443` (لأن Render يفتح HTTPS فقط)
- **Username:** نفس `PROXY_USER`
- **Password:** نفس `PROXY_PASS`
- **Type:** `HTTP Proxy` أو `HTTPS Proxy`

#### على الكمبيوتر (Chrome/Edge)
1. Settings → System → Open proxy settings
2. Manual proxy setup → Use a proxy server = ON
3. Address: `proxy-usa-xxxx.onrender.com` Port: `443`
4. سيطلب اليوزر والباسورد عند أول تصفح

#### Firefox
Settings → Network Settings → Manual proxy configuration
- HTTP Proxy: `proxy-usa-xxxx.onrender.com` Port `443`
- ✅ Also use this proxy for HTTPS
- سيطلب المصادقة تلقائياً

#### على الهاتف (Android/iOS)
WiFi → Modify network → Advanced → Proxy Manual
- Host: `proxy-usa-xxxx.onrender.com`
- Port: `443`

#### للاختبار بـ curl
```bash
curl -x http://USER:PASS@proxy-usa-xxxx.onrender.com:443 -L https://ifconfig.me
curl -x http://USER:PASS@proxy-usa-xxxx.onrender.com:443 https://api.ipify.org
```

يجب أن يظهر IP أمريكي (Ohio/Oregon).

### 4. التأكد أن البروكسي شغال
افتح في المتصفح مباشرة:
```
https://proxy-usa-xxxx.onrender.com/
```
سترى صفحة "Proxy Online - USA" ✅

و `/health` للـ health check:
```
https://proxy-usa-xxxx.onrender.com/health
```

## الأمان
- البروكسي محمي بـ Basic Auth - بدونه يرجع `407 Proxy Authentication Required`
- غير `PROXY_USER` و `PROXY_PASS` من Render → Environment ثم Redeploy
- لا تشارك الرابط بدون الباسورد

## ملاحظات Render Free
- السيرفر ينام بعد 15 دقيقة خمول - أول طلب يصحيه (30 ثانية)
- الباندويث 100GB/شهر مجاناً
- المنطقة: اختر **Ohio** لأقرب نقطة لشرق أمريكا، أو **Oregon** (افتراضي) - كلاهما USA

## الدعم
- GitHub: https://github.com/X5Coder/proxy-usa
- Issues: افتح تذكرة في الريبو

---
Made for X5Coder • Render US Proxy • 2026
