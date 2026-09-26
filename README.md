# IPNET — بروكسي أمريكي بضغطة واحدة

سيرفر بروكسي أمريكي مجاني (GitHub Actions) + برنامج ويندوز + اشتراك للموبايل.

[![YouTube](https://img.shields.io/badge/YouTube-Kareem_X5Coder-red?style=for-the-badge&logo=youtube)](https://www.youtube.com/@Kareem-X5Coder)

المطور: **X5Coder**

## لو عندك رابط مستودع شغال — استخدمه فوراً

### ويندوز
1. حمّل **`IPNET.exe`** من [Releases](../../releases) وشغّله.
2. لو أول مرة: افتح المستودع الأصلي `https://github.com/X5Coder/proxy-usa`
   ودوس **Use this template** واعمل نسختك.
3. الصق رابط **نسختك** في البرنامج ودوس **Start** — هيتفحص الأول وبعدين
   هيفتح Chrome أمريكي لوحده.
4. كل تشغيل بعد كده: نفس الشاشة (الرابط محفوظ) → Start.

### أندرويد (v2rayNG)
1. ثبّت **v2rayNG** (نسخة `arm64-v8a` من المتجر أو GitHub).
2. القائمة ← Subscription settings ← + ← الصق رابط الاشتراك الثابت:
   `https://raw.githubusercontent.com/OWNER/REPO/main/sub.txt`
   (بدّل OWNER/REPO — الرابط الكامل هتلاقيه جاهز للنسخ في ملف `CONNECT.md` جوه المستودع).
3. حدّث الاشتراك ← اختر **IPNET-USA** ← اتصل ووافق على VPN.
4. اتأكد من `ipinfo.io` إنه يقول United States.

## لو عايز سيرفرك الخاص (مرة واحدة — ضغطة واحدة)
1. افتح المستودع الأصلي: `https://github.com/X5Coder/proxy-usa` ودوس **Use this template** واعمل مستودعك.
2. افتح تبويب **Actions** في مستودعك: لو مفيش تشغيل شغال، شغّل **USA Proxy** يدوياً مرة واحدة.
3. بعد دقايق افتح ملف **`CONNECT.md`** في مستودعك: فيه كل حاجة للنسخ (رابط الريبو + رابط ss + رابط الاشتراك + الخطوات).

## إزاي شغال؟

- Actions (أمريكا) يشغل بروكسي HTTP + سيرفر Shadowsocks مشفر، ويكشفهم عبر أنفاق `bore`.
- السيرفر بيفحص نفسه كل دقيقة ويجدد النفق **من أول فشل** وينشر البورت الجديد في `ss_url.txt` + `sub.txt` + `CONNECT.md`.
- **رابط واحد ثابت للأبد**: `sub.txt` (للتطبيقات، يتحدث تلقائياً). البورت يتغير، الرابط لا.
- بعض الشبكات بتحجب `CONNECT` العادي — كل الترافيك عندنا مشفر، مفيش حاجة تتحجب.

## الملفات

| الملف | دوره |
|---|---|
| `x5proxy.py` | برنامج الويندوز (بيتبني `IPNET.exe`) — قراءة فقط، بدون رفع |
| `server.py` | بروكسي HTTP/HTTPS على السيرفر |
| `singbox-server.json` | سيرفر Shadowsocks المشفر |
| `.github/workflows/proxy.yml` | التشغيل + الفحص + الشفاء + توليد الملفات |
| `USER_README.md` | README المستودعات الجديدة |
| `ss-client-template.json` | مثال إعداد عميل يدوي |

## ملاحظات

- SmartScreen "Unknown publisher": **More info ← Run anyway** (مفيش شهادة مدفوعة).
- الباسورد عشوائي لكل مستودع، والبورتات بتتجدد كل ~5 ساعات تلقائياً.
- المستودعات العامة فقط (القراءة من الملفات العامة بدون login).
- لا تمسح `ss_url.txt` — كل حاجة بتقرأ العنوان الحالي منه.

## الحقوق

المستودع الأصلي: `https://github.com/X5Coder/proxy-usa` — المطور **X5Coder**.
ممنوع إزالة الحقوق من البرنامج أو الملفات. تابع الشرح على يوتيوب:
https://www.youtube.com/@Kareem-X5Coder
