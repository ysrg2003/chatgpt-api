# دليل ChatGPT Web API من البداية إلى التشغيل

هذا الدليل يشرح تشغيل `chatgpt-api` كخدمة HTTP فوق جلسة ChatGPT Web داخل Docker Space في Hugging Face. يشرح الدليل ما الذي يفعله المشروع، المتطلبات، إنشاء Space، إعداد كل Secret وVariable، تجهيز Cookies، تشغيل الخدمة محليًا، استدعاء النص والبحث الحي والصور، الاختبار، GitHub Actions، الترقية، التراجع، وتدوير الاعتمادات.

> **حدود مهمة:** هذا المشروع لا يستخدم OpenAI API مباشرة، ولا ينشئ API key من OpenAI. هو أتمتة لجلسة ChatGPT Web عبر Playwright، ولذلك تتبع القدرة والحصة والحالة جلسة ChatGPT والحساب المستخدم داخل المتصفح. Cookies جلسة ChatGPT هي اعتماد عالي الخطورة وتعادل عمليًا جلسة تسجيل الدخول.

## 1. النتيجة التي ستحصل عليها

بعد اتباع الدليل، ستكون لديك خدمة Docker Space بعنوان من الشكل:

```text
https://YOUR_USERNAME-YOUR_SPACE.hf.space
```

وتستطيع استدعاء:

| Endpoint | المصادقة | الوظيفة |
|---|---|---|
| `GET /health` | لا | معرفة هل التطبيق وجلسة Chromium جاهزان |
| `GET /v1/models` | Bearer | فحص عقد النماذج |
| `POST /v1/chat/completions` | Bearer | النص، البحث الحي، والصور |
| `POST /v1/responses` | Bearer | واجهة responses المتوافقة |

## 2. كيف يعمل النظام

يبدأ FastAPI في `main.py`، ثم ينشئ `BrowserGateway` في `browser_gateway.py`. يطلق `BrowserGateway` جلسة Chromium واحدة مستمرة، يحقن Cookies، يفتح ChatGPT، ويرسل الرسائل بالتسلسل تحت قفل واحد. لا يفحص HTML للصور في طلبات النص أو البحث؛ يفعّل `capture_images` فقط عندما يكون الطلب صورة.

الصورة لا تعتبر ناجحة لمجرد وجود عنصر `<img>` في الصفحة. يستخرج النظام الصور المولدة فقط، ويتجاهل favicon وavatar والصور العامة أو القديمة، ثم يعيد `images[].data_url` عندما تتوفر. يمكن للعميل تحويل `data_url` إلى ملف PNG أو JPEG.

> تشغيل عدة طلبات HTTP ممكن، لكن التفاعل داخل جلسة ChatGPT الواحدة متسلسل. طلب توليد صورة طويل قد يجعل طلبات النص اللاحقة تنتظر.

## 3. المتطلبات

| المتطلب | مطلوب؟ | الغرض |
|---|---:|---|
| Python 3.12 أو أحدث | محليًا | تشغيل الاختبارات والخادم خارج Docker |
| Docker | محليًا أو في Space | تشغيل Chromium والخدمة |
| حساب Hugging Face | للنشر | إنشاء Docker Space وإدارة Secrets |
| خطة Hugging Face تسمح بـDocker Space | للنشر | Docker Spaces تعمل على compute؛ راجع خطة الحساب الحالية [1] |
| حساب ChatGPT يملك جلسة صالحة | نعم | الجلسة التي ستستخدمها Playwright |
| Cookies بصيغة Netscape | نعم | تسجيل جلسة ChatGPT داخل Chromium |
| `API_SECRET_KEY` | نعم | حماية endpoint العام |
| GitHub | اختياري | تشغيل workflows الحية والإصدار |

## 4. خريطة المشروع

| المسار | الوظيفة |
|---|---|
| `main.py` | FastAPI endpoints والمصادقة وتحديد النص/البحث/الصورة |
| `browser_gateway.py` | Chromium وPlaywright وإرسال الرسائل واستخراج الصور |
| `Dockerfile` | صورة التشغيل في Hugging Face Docker Space |
| `requirements.txt` | حزم Python |
| `.github/workflows/test-text-search.yml` | اختبار حي للنص والبحث |
| `.github/workflows/test-image.yml` | اختبار حي للصورة ورفع artifact |
| `docs/configuration.md` | خريطة الإعدادات وبطاقات الاعتمادات |
| `docs/integration.md` | استخدام الخدمة من مشروع آخر |
| `docs/operations.md` | التشغيل والاختبارات وGitHub Actions |
| `tests/` | اختبارات offline وHTTP وBrowserGateway |

## 5. بطاقات الاعتمادات والأسرار

### `API_SECRET_KEY` — مفتاح حماية HTTP

**Purpose.** يحمي endpoint مثل `/v1/chat/completions` من الوصول العام. لا علاقة له بمفتاح OpenAI أو Hugging Face.

**Classification.** Secret عالي الحساسية.

**Required or optional.** مطلوب لكل endpoint محمي. `/health` لا يحتاجه.

**Used by.** `main.py` عبر `os.getenv("API_SECRET_KEY", "")`، ثم يقارن قيمة ترويسة `Authorization`.

**Where to obtain it.** لا تحصل عليه من مزود خارجي؛ أنشئ قيمة عشوائية طويلة محليًا:

```bash
openssl rand -hex 32
```

**What to paste.** قيمة عشوائية طويلة، مثل placeholder غير حقيقي:

```text
REPLACE_WITH_A_RANDOM_64_HEX_CHARACTER_SECRET
```

**Where to add it in Hugging Face.**

1. افتح صفحة Space في Hugging Face.
2. اختر **Settings**.
3. افتح **Variables and secrets**.
4. اختر **Secrets** وليس Variables.
5. أنشئ الاسم الدقيق `API_SECRET_KEY` والصق القيمة.
6. احفظ، ثم أعد تشغيل Space إذا لم يبدأ تلقائيًا.

Hugging Face توصي بوضع access tokens وAPI keys والقيم الحساسة في Secrets، بينما Variables للقيم غير الحساسة [1]. قيمة Secret لا تظهر بعد حفظها.

**Minimal verification.**

```bash
export CHATGPT_SPACE_URL="https://YOUR_USERNAME-YOUR_SPACE.hf.space"
export CHATGPT_API_SECRET_KEY="REPLACE_WITH_YOUR_SECRET"
curl -fsS "$CHATGPT_SPACE_URL/health"
curl -fsS "$CHATGPT_SPACE_URL/v1/models" \
  -H "Authorization: Bearer $CHATGPT_API_SECRET_KEY"
```

**Expected success.** يعيد `/health` JSON فيه `ready: true`، ويعيد `/v1/models` HTTP 200 دون خطأ مصادقة.

**Common failures.** HTTP 401 يعني أن الاسم أو القيمة غير متطابقين أو أن ترويسة Bearer مفقودة. HTTP 503 يعني أن التطبيق أو Chromium غير جاهز. لا تختبر القيمة بطباعتها؛ افحص status code فقط.

**Rotation and revocation.** أنشئ قيمة جديدة، حدّث Secret في Space، حدّث كل العملاء، نفذ smoke test، ثم اعتبر القيمة القديمة ملغاة. إذا ظهرت القيمة في سجل أو محادثة، بدّلها فورًا.

### `CHATGPT_COOKIES_NETSCAPE` — جلسة ChatGPT Web

**Purpose.** يمرر جلسة ChatGPT إلى Chromium حتى يستطيع `BrowserGateway` فتح ChatGPT وإرسال الطلبات.

**Classification.** Secret/session credential شديد الخطورة. لا تضعه في Git أو Issue أو artifact.

**Required or optional.** مطلوب للتشغيل الحقيقي. بدونه قد يبدأ الخادم، لكن لا يستطيع تنفيذ تفاعل ChatGPT.

**Used by.** `browser_gateway.py` عبر `browser_settings_from_env()` و`parse_netscape_cookies()`.

**Where to obtain it.**

1. افتح [chatgpt.com](https://chatgpt.com) في متصفحك.
2. سجّل الدخول إلى الحساب الذي تملك حق استخدامه.
3. استخدم أداة موثوقة ومراجعة جيدًا لتصدير Cookies للموقع بصيغة Netscape/cookies.txt. لا ترفع الملف إلى أي خدمة تحويل عامة.
4. افتح الملف محليًا وتحقق من أنه يبدأ بتنسيق Netscape، دون نسخ محتواه في سجل أو محادثة.
5. الصق المحتوى كاملًا مرة واحدة في Secret باسم `CHATGPT_COOKIES_NETSCAPE` داخل Space.
6. احذف ملف التصدير المحلي أو خزنه في مدير أسرار مشفر بعد التأكد من نجاح التشغيل.

**What to paste.** ملف Netscape placeholder شكلي، وليس قيمة حقيقية:

```text
# Netscape HTTP Cookie File
.example.com	TRUE	/	TRUE	0	COOKIE_NAME	REPLACE_WITH_COOKIE_VALUE
```

**Minimal verification.**

```bash
curl -fsS "$CHATGPT_SPACE_URL/health"
```

**Expected success.** `ready: true` بعد اكتمال Chromium وفتح جلسة ChatGPT. هذا لا يضمن أن الحصة متاحة؛ اختبر طلبًا نصيًا قصيرًا بعده.

**Common failures.** رسالة `CHATGPT_COOKIES_NETSCAPE is not configured` تعني أن Secret مفقود. رسالة `contains no valid cookies` تعني تنسيقًا غير صالح. ظهور صفحة تسجيل الدخول أو `Locator.click` timeout يعني أن Cookies انتهت أو أن جلسة ChatGPT تعرض شاشة مختلفة؛ صدّر Cookies جديدة، ثم أعد تشغيل Space.

**Expiry and revocation.** تنتهي Cookies عند تسجيل الخروج أو تغيير الجلسة أو إبطالها من ChatGPT. لإبطالها، سجّل الخروج من كل الجلسات أو ألغِ الجلسة من إعدادات الحساب، ثم حدّث Secret.

**After accidental exposure.** اعتبر الحساب مكشوفًا: سجّل الخروج من كل الجلسات، ألغِ Cookies القديمة، صدّر Cookies جديدة، بدّل `API_SECRET_KEY`، وتحقق من عدم وجودها في GitHub Actions artifacts أو logs.

### `API_KEY` — الاسم التوافقي القديم

**Exact name.** `API_KEY`.

**Purpose.** اسم توافق قديم لنفس Bearer secret الذي تحمي به الخدمة endpoints. استخدم `API_SECRET_KEY` في الإعدادات الجديدة، ولا تنشئ مفتاحين مختلفين ظنًا أنهما مزودان مختلفان.

**Classification.** Secret.

**Required or optional.** اختياري للتوافق مع إعدادات قديمة؛ لا تعتمد عليه إذا كان الإصدار الحالي يقرأ `API_SECRET_KEY` فقط.

**Used by.** طبقة التوافق القديمة أو نسخ سابقة من `main.py` عند تفعيلها.

**Where to obtain it.** أنشئه محليًا مثل `API_SECRET_KEY` باستخدام `openssl rand -hex 32`، أو اجعله نفس القيمة عمدًا عند ترحيل إعداد قديم.

**Safe placeholder and format.**

```text
REPLACE_WITH_A_RANDOM_64_HEX_CHARACTER_SECRET
```

**Exact storage location.** Hugging Face Space → **Settings → Variables and secrets → Secrets** → `API_KEY`. لا تضعه في Variables أو Git.

**Minimal health check.** نفّذ `GET /v1/models` مع Bearer value؛ يجب أن يعيد 200 إذا كانت نسخة التطبيق تقرأ الاسم القديم. إذا كان الإصدار الحالي لا يقرأه، انقل القيمة إلى `API_SECRET_KEY`.

**Common failure and fix.** HTTP 401 مع `API_KEY` يعني أن الخدمة تتوقع `API_SECRET_KEY`؛ أضف الاسم الحديث، أعد تشغيل Space، ثم اختبره.

**Rotation and revocation.** دوّر الاسمين إذا كانا موجودين، حدّث العملاء، ثم احذف الاسم القديم بعد نجاح smoke test. عند exposure ألغِ القيمة فورًا.

### Hugging Face Access Token — إدارة Hub فقط

**Purpose.** يستخدم لإدارة Space، استنساخ repository، دفع commits، ضبط Secrets، وإعادة التشغيل عبر Hub API. لا يُرسل إلى `/v1/chat/completions` ولا يقوم بدور `API_SECRET_KEY`.

**Classification.** Secret عالي الحساسية.

**Where to obtain it.**

1. افتح [Hugging Face Settings → Access Tokens](https://huggingface.co/settings/tokens).
2. اختر إنشاء User Access Token.
3. امنح أقل صلاحية ممكنة؛ يلزم write فقط إذا كنت سترفع أو تعدّل repository، بينما read يكفي للقراءة [2].
4. انسخ القيمة مرة واحدة إلى مدير أسرار أو إلى تسجيل الدخول المحلي، ولا تضعها في URL أو ملف مستودع.

**Safe local setup.** الأفضل استخدام تسجيل الدخول الرسمي:

```bash
hf auth login
hf auth whoami
```

بديل آمن للعملية الحالية هو متغير بيئة مؤقت لا يُطبع:

```bash
export HF_TOKEN="REPLACE_WITH_HF_WRITE_TOKEN"
```

**Verification.** استخدم `hf auth whoami` أو طلب Hub لا يعرض القيمة. لا تستخدم token اختبار Hub في تطبيق ChatGPT نفسه.

**Rotation and revocation.** افتح صفحة Access Tokens، احذف أو revoke القيمة القديمة، أنشئ قيمة جديدة بصلاحية أقل، ثم حدّث CI أو جهازك.

### GitHub Actions Secrets

إذا شغلت workflows من repository `ysrg2003/chatgpt-api`:

1. افتح repository في GitHub.
2. اختر **Settings → Secrets and variables → Actions**.
3. اختر **Secrets** ثم **New repository secret**.
4. أنشئ `API_SECRET_KEY` بالقيمة المطابقة لـSpace.
5. شغّل workflow من **Actions → Run workflow**.

GitHub يوضح أن Secrets تُضاف من إعدادات Actions وتُستهلك داخل workflow عبر `${{ secrets.NAME }}`، ولا ينبغي تمريرها في command line أو طباعتها [3].

## 6. المتغيرات غير السرية

| الاسم | النوع | default | الوظيفة | مكان الإعداد |
|---|---|---:|---|---|
| `PORT` | number | `7860` | منفذ Uvicorn داخل Docker | Variable أو Docker |
| `CHATGPT_HEADLESS` | boolean | `true` | تشغيل Chromium بلا واجهة | Variable |
| `CHATGPT_READY_TIMEOUT` | seconds | `180` | انتظار جاهزية الجلسة | Variable |
| `CHATGPT_REQUEST_TIMEOUT` | seconds | `210` | مهلة التفاعل النصي الافتراضية | Variable |
| `MAX_PROMPT_CHARS` | number | `50000` | الحد الأعلى للبرومبت | Variable |
| `RATE_LIMIT_REQUESTS` | number | `20` | طلبات كل نافذة لكل عميل | Variable |
| `RATE_LIMIT_WINDOW_SECONDS` | seconds | `60` | طول نافذة rate limiter | Variable |
| `LOG_LEVEL` | enum | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Variable |
| `ALLOWED_ORIGINS` | comma-separated URLs | فارغ | CORS origins | Variable |

هذه القيم غير سرية، لكن لا تغيّر مهلة الصورة إلى أقل من الزمن المطلوب لتوليدها. لا تستخدم Variables لـCookies أو API secrets لأن Variables عامة وقابلة للرؤية، بينما Secrets خاصة [1].

### بطاقات المتغيرات التفصيلية

كل بطاقة هنا تصف الاسم الدقيق الذي يقرأه التطبيق، ونوعه، ومكانه، وتأثيره، وطريقة التحقق منه.

#### `PORT`

| الحقل | القيمة |
|---|---|
| Type / default | number / `7860` |
| Allowed values | رقم منفذ موجب؛ استخدم `7860` في Docker Space |
| Set location | Hugging Face Variable أو `--port` محليًا |
| Consumer / effect | Uvicorn وDocker؛ يحدد منفذ الاستماع |
| Safe example | `PORT=7860` |
| Verification | `curl http://127.0.0.1:7860/health` أو افتح URL Space |
| Common mistake | استخدام منفذ لا يطابق `app_port: 7860`؛ صححه إلى `7860` ثم أعد التشغيل |

#### `CHATGPT_HEADLESS`

| الحقل | القيمة |
|---|---|
| Type / default | boolean / `true` |
| Allowed values | `true` أو `false` |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | إعداد Chromium؛ `true` مناسب للخادم بلا شاشة |
| Safe example | `CHATGPT_HEADLESS=true` |
| Verification | logs تشير إلى تشغيل Chromium دون انتظار واجهة مرئية |
| Common mistake | قيمة `yes` أو `1` غير المدعومة؛ استخدم `true` أو `false` حرفيًا |

#### `CHATGPT_READY_TIMEOUT`

| الحقل | القيمة |
|---|---|
| Type / default | seconds / `180` |
| Allowed values | عدد صحيح موجب |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | مهلة فتح ChatGPT والتحقق من مربع الإدخال |
| Safe example | `CHATGPT_READY_TIMEOUT=180` |
| Verification | `/health` ينتقل من initializing إلى `ready: true` ضمن المهلة |
| Common mistake | قيمة قصيرة أثناء cold start؛ زدها بدل إعادة إرسال الطلبات المتكررة |

#### `CHATGPT_REQUEST_TIMEOUT`

| الحقل | القيمة |
|---|---|
| Type / default | seconds / `210` |
| Allowed values | عدد صحيح موجب، أكبر من زمن الاستجابة المتوقع |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | مهلة الطلب الواحد؛ تؤثر خصوصًا على البحث والصورة |
| Safe example | `CHATGPT_REQUEST_TIMEOUT=210` |
| Verification | طلب نص أو بحث ينتهي قبل timeout |
| Common mistake | خفضها لزمن قصير ثم اعتبار الصورة فاشلة؛ أعدها إلى `210` أو قيمة أعلى من سياسة العميل |

#### `MAX_PROMPT_CHARS`

| الحقل | القيمة |
|---|---|
| Type / default | number / `50000` |
| Allowed values | عدد صحيح لا يقل عن حد التطبيق |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | يرفض prompts الأطول لحماية الذاكرة والمهلة |
| Safe example | `MAX_PROMPT_CHARS=50000` |
| Verification | prompt أقصر ينجح، والطويل يعيد خطأ validation واضحًا |
| Common mistake | إرسال transcript أكبر من الحد؛ لخصه أو زد القيمة بحذر |

#### `RATE_LIMIT_REQUESTS`

| الحقل | القيمة |
|---|---|
| Type / default | number / `20` |
| Allowed values | صفر لتعطيل limiter أو عدد صحيح موجب |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | عدد الطلبات لكل client خلال نافذة واحدة |
| Safe example | `RATE_LIMIT_REQUESTS=20` |
| Verification | الطلبات ضمن الحد تنجح؛ الزائد يعيد 429 |
| Common mistake | رفعه لتجاوز quota ChatGPT؛ هذا لا يرفع quota ويزيد ضغط الجلسة |

#### `RATE_LIMIT_WINDOW_SECONDS`

| الحقل | القيمة |
|---|---|
| Type / default | seconds / `60` |
| Allowed values | عدد صحيح موجب |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | طول نافذة fixed-window limiter |
| Safe example | `RATE_LIMIT_WINDOW_SECONDS=60` |
| Verification | بعد انتهاء النافذة يمكن لعميل مقيد إرسال طلب جديد |
| Common mistake | قيمة `0` أو سالبة؛ استخدم `60` أو أكبر |

#### `LOG_LEVEL`

| الحقل | القيمة |
|---|---|
| Type / default | enum / `INFO` |
| Allowed values | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | مستوى سجلات Python؛ `DEBUG` قد يزيد التفاصيل الحساسة |
| Safe example | `LOG_LEVEL=INFO` |
| Verification | runtime logs تظهر الرسائل بالمستوى المختار دون Secrets |
| Common mistake | ترك `DEBUG` في الإنتاج؛ استخدم `INFO` ثم احذف logs الحساسة |

#### `ALLOWED_ORIGINS`

| الحقل | القيمة |
|---|---|
| Type / default | comma-separated URLs / فارغ |
| Allowed values | origins كاملة مثل `https://app.example.com`; لا تستخدم مسارًا أو token |
| Set location | Hugging Face Variable أو `.env` |
| Consumer / effect | FastAPI CORS؛ الفارغ يمنع متصفحًا غير مصرح له من cross-origin |
| Safe example | `ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com` |
| Verification | طلب browser من origin مسموح يحصل على CORS headers، وغيره لا يحصل عليها |
| Common mistake | وضع `*` مع توقع حماية؛ اذكر origins صراحةً ولا تضع Secrets في URL |


## 7. إنشاء Docker Space من الصفر

تحتاج إلى حساب Hugging Face وخطة تسمح بـDocker Space؛ توضح وثائق Spaces أن Docker وGradio يعملان على compute ويتطلب إنشاءهما خطة مدفوعة للحسابات الشخصية، مع استثناءات محددة حسب الخطة [1].

### من واجهة Hugging Face

1. افتح [Spaces](https://huggingface.co/spaces) واختر **Create new Space**.
2. أدخل اسم Space والمالك.
3. اختر visibility المناسبة؛ لا تجعل Space عامة إذا كان repository يحتوي إعدادات أو artifacts حساسة.
4. اختر SDK: **Docker**.
5. اختر hardware المتاح ثم أنشئ Space.
6. ارفع ملفات هذا المستودع إلى branch `main`.
7. افتح **Settings → Variables and secrets** وأضف `API_SECRET_KEY` و`CHATGPT_COOKIES_NETSCAPE` كـSecrets.
8. أضف المتغيرات غير الحساسة كـVariables.
9. انتظر build ثم افحص runtime و`/health`.

كل commit جديد في Space يعيد build/restart تلقائيًا بحسب دورة Spaces [1].

### من Git

```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE
cd YOUR_SPACE
cp -a /path/to/chatgpt-api/. .
git add .
git commit -m "Deploy chatgpt-api"
git push
```

لا تضع `.env` أو ملف Cookies في working tree المتعقب. Secrets تُضبط من Settings أو Hub API، وليس عبر commit.

## 8. التشغيل المحلي

### تثبيت الحزم

```bash
git clone https://github.com/ysrg2003/chatgpt-api.git
cd chatgpt-api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

### إعداد `.env`

```bash
cp .env.example .env
```

ضع Secret وCookies في `.env` المحلي فقط. تحقق من أن `.env` غير متعقب:

```bash
git ls-files .env
```

يجب ألا يطبع الأمر شيئًا.

### تشغيل الخادم

```bash
set -a
source .env
set +a
uvicorn main:app --host 0.0.0.0 --port "${PORT:-7860}"
```

في طرفية أخرى:

```bash
curl -fsS http://127.0.0.1:7860/health
```

## 9. عقد API

### مصادقة الطلب

```http
Authorization: Bearer YOUR_API_SECRET_KEY
Content-Type: application/json
```

### نص

```bash
curl -fsS -X POST "$CHATGPT_SPACE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $CHATGPT_API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"قل فقط: نجح اختبار النص"}]}'
```

توقع وجود:

```json
{
  "choices": [{"message": {"content": "نجح اختبار النص"}}],
  "images": []
}
```

### بحث حي

أرسل prompt يتضمن مؤشرات البحث، أو أضف العبارة صراحةً:

```bash
curl -fsS -X POST "$CHATGPT_SPACE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $CHATGPT_API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ابحث في الويب بحث حي: ما آخر موديل Anthropic AI؟"}]}'
```

الاستجابة نصية. وجود كلمات مثل `sources` أو روابط لا يضمن صحة الادعاء؛ راجع المصادر بنفسك قبل اتخاذ قرار حساس.

### صورة

```bash
curl -fsS -X POST "$CHATGPT_SPACE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $CHATGPT_API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"generate image of a wise stickman reading a book in a library"}]}' \
  -o response.json
```

ابحث في `response.json` عن `images[].data_url`. فك الجزء بعد `base64,` إلى ملف فقط بعد التحقق من `mime_type`:

```bash
python - <<'PY'
import base64, json
from pathlib import Path
body = json.loads(Path("response.json").read_text())
data_url = body["images"][0]["data_url"]
_, encoded = data_url.split(",", 1)
Path("generated.png").write_bytes(base64.b64decode(encoded))
PY
file generated.png
```

لا تعتبر الاستجابة ناجحة إذا كانت `images` فارغة أو إذا كان العنصر favicon/avatar. حد الصور تابع لحساب ChatGPT Web، وليس لوجود `API_SECRET_KEY` مختلف.

## 10. الاختبارات

### اختبارات offline

```bash
python -m compileall -q main.py browser_gateway.py tests
API_SECRET_KEY=test-secret python -m unittest discover -s tests -v
```

### GitHub Actions

| Workflow | ما يختبره | الحصة |
|---|---|---|
| `test-text-search.yml` | النص والبحث الحي | يستهلك ChatGPT messages/search |
| `test-image.yml` | توليد الصورة وتنزيل PNG | يستهلك حصة توليد الصور |

أضف `API_SECRET_KEY` إلى GitHub Actions Secrets، ثم افتح **Actions** واختر workflow ثم **Run workflow**. لا تعتمد على اللون الأخضر وحده؛ نزّل artifact وافحص JSON وحجم الملف وصيغته. لا ترفع Cookies إلى GitHub Actions إلا إذا كانت السياسة الأمنية لديك تسمح بذلك؛ الأفضل أن تبقى Cookies داخل Space.

## 11. التزامن والحدود

يقبل FastAPI عدة اتصالات، لكن `BrowserGateway` يحمي جلسة Chromium بقفل واحد. الطلب الثاني ينتظر الأول. طلب الصورة قد يستغرق دقائق، فيؤخر النص والبحث. توجد أيضًا حدود ChatGPT Web، rate limiter المحلي، مهلة العميل، وحالة نوم/إيقاف Space.

لرفع القدرة، استخدم replicas مستقلة، بحيث يكون لكل replica Chromium وCookies منفصلة، ثم وزع الطلبات بينها من router. لا تزل القفل من جلسة واحدة؛ إزالة القفل قد تخلط الرسائل والردود والصور بين الطلبات.

## 12. استكشاف الأخطاء

| العرض | السبب المحتمل | الإجراء |
|---|---|---|
| `/health` يعيد `503` | build أو Chromium أو Cookies غير جاهزة | افحص runtime، انتظر، ثم راجع logs وSecrets |
| `401 Invalid API Key` | `API_SECRET_KEY` غير مطابق أو Bearer ناقص | طابق الاسم والقيمة وأعد التشغيل |
| `CHATGPT_COOKIES_NETSCAPE is not configured` | Secret مفقود | أضف Secret بالاسم الحرفي |
| `contains no valid cookies` | ملف غير Netscape أو أسطر ناقصة | صدّر الملف مجددًا ولا تستخدم نسخًا يدوية ناقصة |
| تسجيل دخول بدل ChatGPT | Cookies منتهية أو لحساب آخر | سجّل الدخول، صدّر Cookies جديدة، أعد التشغيل |
| `Locator.click` timeout | تغيرت الصفحة أو جلسة غير صالحة أو overlay | افحص Cookie، أعد التشغيل، ثم صدّر Cookie جديدة |
| النص يعمل والصورة تعيد quota | حد توليد الصور في ChatGPT Web | انتظر reset أو استخدم حسابًا يملك الحصة؛ لا تغيّر API secret فقط |
| الصورة `images=[]` | التوليد لم ينتهِ أو الفلتر رفض asset غير مولد | انتظر، أعد الطلب بمهلة مناسبة، افحص رسالة الرد |
| `429` من API | rate limit أو quota | انتظر cooldown، خفّض التوازي، أو استخدم replica أخرى |
| build Docker يفشل | dependency أو browser install | راجع logs وDockerfile وأعد build بعد تثبيت dependency |

## 13. الترقية والتراجع

قبل الترقية احفظ commit الحالي وراجع diff:

```bash
git status --short
git log -5 --oneline
git tag --list
```

للتحديث:

```bash
git pull --ff-only
python -m compileall -q main.py browser_gateway.py tests
API_SECRET_KEY=test-secret python -m unittest discover -s tests -v
```

للتراجع محليًا إلى release معروف:

```bash
git fetch --tags
git checkout v1.1.2-image-boundary-docs
```

في Space، ادفع commit أو tag المعروف إلى branch النشر، ثم انتظر build جديدًا وافحص `/health`. لا تخلط بين rollback للكود وrollback للـCookies؛ إذا كانت Cookies منتهية، يلزم تدويرها مستقلاً.

## 14. التنظيف والأمان

احذف ملفات Cookies المحلية بعد تخزينها في مكان آمن. افحص repository قبل الدفع:

```bash
git status --short
git ls-files .env
find . -maxdepth 3 -type f \( -name '*.env' -o -name '*cookie*' -o -name '*response*.json' \) -print
```

لا ترفع `response.json` إذا احتوى base64 أو URLs حساسة. احذف GitHub artifacts التي تحتوي ردودًا أو صورًا حساسة، ودوّر `API_SECRET_KEY` وCookies عند التعرض.

## 15. مراجع رسمية

[1]: https://huggingface.co/docs/hub/spaces-overview#managing-secrets "Hugging Face Spaces: creating, secrets, variables, duplication, and lifecycle"
[2]: https://huggingface.co/docs/huggingface_hub/en/quick-start#authentication "Hugging Face Hub Quickstart: authentication and token permissions"
[3]: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions "GitHub Actions: using secrets"
[4]: https://github.com/ysrg2003/chatgpt-api "chatgpt-api source repository"
