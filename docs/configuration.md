# إعداد `chatgpt-api`

هذا الملف يشرح خريطة القيم الأساسية. للمسار الكامل من إنشاء Space إلى إعداد Secrets وCookies وتشغيل النص والبحث والصورة والاختبار والتدوير، راجع **[دليل ChatGPT الكامل من البداية إلى النهاية](chatgpt-guide.md)**. تُحفظ القيم الحساسة في **Hugging Face Space Secrets** أو في مدير أسرار مكافئ، ولا تُحفظ في Git.

## خريطة الإعداد

| الاسم | النوع | مطلوب | القيمة الافتراضية | المستهلك |
|---|---|---:|---|---|
| `API_SECRET_KEY` | Secret | نعم | لا يوجد | حماية نقاط API العامة |
| `CHATGPT_COOKIES_NETSCAPE` | Secret | نعم عند عدم استخدام Storage State | فارغ | جلسة Playwright داخل ChatGPT |
| `CHATGPT_STORAGE_STATE_JSON` | Secret | اختياري؛ يتغلب على Netscape عند وجوده | فارغ | Storage State كامل لـPlaywright داخل ChatGPT |
| `PORT` | Variable | لا | `7860` | منفذ Uvicorn وDocker |
| `CHATGPT_HEADLESS` | Variable | لا | `true` | تشغيل Chromium بلا واجهة |
| `CHATGPT_READY_TIMEOUT` | Variable | لا | `180` | مهلة تجهيز الجلسة بالثواني |
| `CHATGPT_REQUEST_TIMEOUT` | Variable | لا | `210` | مهلة الطلب الواحد بالثواني |
| `MAX_PROMPT_CHARS` | Variable | لا | `50000` | الحد الأقصى لطول البرومبت |
| `RATE_LIMIT_REQUESTS` | Variable | لا | `20` | عدد الطلبات لكل نافذة |
| `RATE_LIMIT_WINDOW_SECONDS` | Variable | لا | `60` | طول نافذة تحديد المعدل |
| `LOG_LEVEL` | Variable | لا | `INFO` | مستوى السجل |
| `ALLOWED_ORIGINS` | Variable | لا | فارغ | مصادر CORS المسموح بها |

## بطاقة الاعتماد: `API_SECRET_KEY`

**Exact name:** `API_SECRET_KEY`.

**Classification:** Secret؛ مفتاح داخلي لحماية واجهة الخادم، وليس مفتاح OpenAI أو Hugging Face.

**Required or optional:** مطلوب. إذا كان فارغًا، ترفض الواجهة الطلبات المحمية بـ401.

**Used by:** `main.py` في دالة التحقق من ترويسة `Authorization`.

**Where to obtain it:** لا يُشترى من مزود خارجي. أنشئه محليًا بقيمة عشوائية طويلة:

```bash
openssl rand -hex 32
```

**Account and permissions:** لا يحتاج إلى حساب خارجي؛ يجب أن يعرفه العميل الذي يستدعي الـAPI فقط.

**Safe placeholder and format:** قيمة hex عشوائية مثل `replace-with-a-long-random-secret` في `.env.example`. لا تستخدم قيمة قصيرة أو قيمة منشورة.

**Exact storage location:** Hugging Face Space → Settings → Variables and secrets → Secrets → `API_SECRET_KEY`.

**How the code reads it:** `os.getenv("API_SECRET_KEY", "")`.

**Minimal health check:**

```bash
curl -i https://YOUR_SPACE.hf.space/health
curl -i https://YOUR_SPACE.hf.space/v1/models \
  -H "Authorization: Bearer YOUR_API_SECRET_KEY"
```

**Expected success:** `/health` يعيد 200 عندما تصبح جلسة المتصفح جاهزة، و`/v1/models` يعيد 200 مع قائمة النماذج.

**Common failure and fix:** 401 تعني أن الترويسة غير موجودة أو لا تطابق الـSecret؛ راجع الاسم حرفيًا وأعد تشغيل Space.

**Expiry, rotation, and revocation:** لا تنتهي القيمة تلقائيًا، لكن استبدلها دوريًا أو فور الشك في انكشافها. غيّر Secret، ثم حدّث العملاء الذين يستخدمونه.

**What to do after accidental exposure:** احذف القيمة القديمة فورًا، أنشئ قيمة جديدة، أعد تشغيل Space، ولا تضع القيمة في Issue أو log أو commit.

## بطاقة الاعتماد: `CHATGPT_STORAGE_STATE_JSON`

**Exact name:** `CHATGPT_STORAGE_STATE_JSON`.

**Classification:** Secret شديد الحساسية؛ ملف Playwright Storage State كامل وقد يحتوي Cookies قابلة لإعادة استخدام الجلسة.

**Required or optional:** اختياري. إذا وُجد وكان JSON صالحًا، يستخدمه `browser_gateway.py` بدل تحميل `CHATGPT_COOKIES_NETSCAPE`، ولذلك لا يحتاج Space إلى أن تجمع الطريقتين لنفس الحساب.

**Used by:** `browser_settings_from_env()` و`BrowserGateway.start()`؛ يمرر JSON إلى `browser.new_context(storage_state=...)` ولا يطبع القيم في السجل.

**Where to obtain it:** أنشئ Chrome Profile اختباريًا منفصلًا، سجّل الدخول إلى ChatGPT، ثم صدّر Playwright Storage State باستخدام `context.storage_state(path=..., indexed_db=True)` إن كان إصدار Playwright يدعم ذلك. لا تصدّر Profile حسابك الرئيسي ولا تضع الملف في Git.

**Expected format:** كائن JSON يحتوي عادةً على `cookies` ومصفوفة `origins` اختيارية. يجب أن تكون كل Cookie مشتملة على `name`, `value`, `domain`, و`path`.

**Exact storage location:** Hugging Face Space → **Settings → Variables and secrets → Secrets** → `CHATGPT_STORAGE_STATE_JSON`. الصق محتوى JSON كاملًا في Secret، لا في Variable.

**Priority rule:** إذا كان `CHATGPT_STORAGE_STATE_JSON` موجودًا وصالحًا، يفضله التطبيق على `CHATGPT_COOKIES_NETSCAPE`. هذا مهم لأن Storage State يمكن أن يحمل حالة مصادق عليها لا تنتقل دائمًا عبر Netscape Cookies وحدها.

**Minimal health check:**

```bash
curl -sS https://YOUR_SPACE.hf.space/health
```

**Expected success:** تصبح الخدمة جاهزة ويظهر `ready: true`، ثم يعيد اختبار نص بسيط Assistant response. ظهور composer وحده ليس دليلًا كافيًا.

**Common failure and fix:** رسالة `CHATGPT_STORAGE_STATE_JSON is invalid` تعني أن Secret ليس JSON صالحًا أو تم قصه أثناء اللصق. ورسالة `ChatGPT input was not found; session may be expired` تعني أن Storage State انتهت أو أن الحساب يحتاج تسجيل دخول يدويًا من جديد.

**Expiry, rotation, and revocation:** اعتبر الملف مساويًا لجلسة تسجيل الدخول. عند انتهاء الجلسة، سجّل الدخول في Profile اختباري جديد، صدّر State جديدًا، استبدل Secret، ثم أعد تشغيل Space. عند الشك في انكشافه، سجّل الخروج وألغِ الجلسة فورًا واحذف Secret القديم.

**What to do after accidental exposure:** سجّل الخروج من جلسات ChatGPT، ألغِ الجلسات النشطة، احذف Secret، أنشئ Storage State جديدًا من Profile منفصل، ولا ترفع الملف في Issue أو commit.

## بطاقة الاعتماد: `CHATGPT_COOKIES_NETSCAPE`

**Exact name:** `CHATGPT_COOKIES_NETSCAPE`.

**Classification:** Secret شديد الحساسية؛ يمثل جلسة تسجيل دخول ChatGPT.

**Required or optional:** مطلوب لتشغيل المتصفح الخلفي.

**Used by:** `browser_gateway.py` لتحويل ملف Netscape إلى Cookies ثم حقنه في Chromium.

**Where to obtain it:** سجّل الدخول إلى [chatgpt.com](https://chatgpt.com) في متصفحك، ثم استخدم أداة موثوقة لتصدير Cookies بصيغة Netscape/cookies.txt. صدّر Cookies الخاصة بالموقع المتصل بجلسة ChatGPT.

**Account and permissions:** الحساب الذي تصدّر منه Cookies هو الحساب الذي سيستخدمه النظام؛ لا تستخدم حسابًا لا تملك تفويضًا لاستخدامه.

**Step-by-step acquisition:**

1. افتح `https://chatgpt.com` وسجّل الدخول يدويًا.
2. استخدم إضافة تصدير Cookies موثوقة ومراجعة جيدًا، واختر صيغة Netscape.
3. افتح الملف الناتج نصيًا وتحقق من أنه نص Netscape، دون مشاركته.
4. الصق المحتوى كاملًا في Secret باسم `CHATGPT_COOKIES_NETSCAPE`.
5. احذف ملف التصدير المحلي بعد حفظ Secret.

**Safe placeholder and format:** يبدأ عادةً بتعليق Netscape مثل `# Netscape HTTP Cookie File` ثم أسطر مفصولة بعلامات تبويب. لا تضعه في `.env` المتعقب أو README.

**Exact storage location:** Hugging Face Space → Settings → Variables and secrets → Secrets → `CHATGPT_COOKIES_NETSCAPE`.

**How the code reads it:** `browser_settings_from_env()` ثم `parse_netscape_cookies()` في `browser_gateway.py`.

**Minimal health check:**

```bash
curl -sS https://YOUR_SPACE.hf.space/health
```

**Expected success:** `{"ready":true}` بعد اكتمال إقلاع Chromium.

**Common failure and fix:** `CHATGPT_COOKIES_NETSCAPE is not configured` تعني أن Secret مفقود؛ و`contains no valid cookies` تعني أن الصيغة أو المحتوى غير صالح. صدّر Cookies جديدة إذا انتهت الجلسة.

**Expiry, rotation, and revocation:** قد تنتهي Cookies عند تسجيل الخروج أو تغيير الجلسة أو انتهاء صلاحيتها. لإبطالها، سجّل الخروج من ChatGPT أو غيّر إعدادات الجلسة، ثم استبدل Secret.

**What to do after accidental exposure:** اعتبر الجلسة مخترقة؛ سجّل الخروج من ChatGPT من كل الجلسات، ألغِ الجلسة، صدّر Cookies جديدة، واحذف القيمة القديمة من Space.

## إعداد محلي

ابدأ من جذر المشروع:

```bash
cp .env.example .env
```

ضع القيم الحقيقية في `.env` محليًا فقط، وتأكد من أن الملف غير متعقب:

```bash
git ls-files .env
```

يجب ألا يطبع الأمر شيئًا. لا تستخدم `.env` في صورة Docker أو commit عام.

## إعداد Hugging Face Space

في إعدادات Space، ضع Secrets فقط للقيم الحساسة، وVariables للقيم غير الحساسة. لا تضع Cookies أو API secret في قسم Variables العام. بعد التعديل استخدم **Restart**، ثم انتظر حتى يصبح runtime `RUNNING` واختبر `/health`.
