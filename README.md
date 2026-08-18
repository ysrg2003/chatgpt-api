---
title: ChatGPT Web API
description: OpenAI-compatible API backed by a ChatGPT browser session.
sdk: docker
app_port: 7860
---

# ChatGPT Web API على Hugging Face

> أدلة المشروع: [الإعداد والأسرار](docs/configuration.md) · [التشغيل والنشر](docs/operations.md) · [التكامل من مشروع آخر](docs/integration.md) · [نسخة Space المضمنة](vendor/chatgpt-space/README.md)

هذا المشروع يحوّل جلسة ChatGPT في المتصفح إلى REST API متوافقة مع البنية الشائعة لـ OpenAI. يعتمد الخادم على **FastAPI** و**Playwright** وChromium headless داخل Docker. الفكرة مستوحاة من مشروع [cognitive_prosthetic][1]، وجرى تكييفها لبيئة Hugging Face Space بدل التشغيل المحلي التفاعلي.

> هذا ليس منتجًا رسميًا من OpenAI. إنه أداة أتمتة لواجهة الويب مخصصة للتجارب الشخصية والتعليمية. قد تتغير واجهة ChatGPT أو شروط الخدمة، وقد تتوقف الأتمتة دون سابق إنذار. لا تستخدمه لتجاوز حدود أو ضوابط مزود الخدمة، ولا تعتبره بديلًا رسميًا لواجهة OpenAI.

## كيف يعمل

يبدأ التطبيق FastAPI على المنفذ 7860. وعند بدء دورة الحياة، يطلق جلسة Chromium واحدة داخل Xvfb، يحقن كوكيز ChatGPT من Secret بصيغة Netscape، ثم يتحقق من وجود مربع الإدخال. كل طلب يمر عبر قفل واحد إلى جلسة المتصفح نفسها، لأن التفاعل مع صفحة واحدة لا يُفترض أن يتداخل بين طلبين. بعد إرسال الرسالة، ينتظر الخادم استقرار نص آخر رد من المساعد قبل إرجاع JSON.

لا تُحفظ ملفات profile أو الكوكيز في المستودع. في HF يجب وضع القيم الحساسة في **Settings → Secrets and variables → Secrets**. الحد الأدنى المطلوب هو:

| المتغير | المطلوب | الوظيفة |
|---|---:|---|
| `API_SECRET_KEY` | نعم | Bearer token لحماية API |
| `CHATGPT_COOKIES_NETSCAPE` | نعم | جلسة ChatGPT بصيغة Netscape cookie export |
| `CHATGPT_HEADLESS` | لا | الافتراضي `true` لتشغيل Chromium في بيئة الخادم |
| `CHATGPT_REQUEST_TIMEOUT` | لا | مهلة الرد بالثواني، الافتراضي 210 |
| `RATE_LIMIT_REQUESTS` | لا | عدد الطلبات لكل نافذة، الافتراضي 20 |
| `RATE_LIMIT_WINDOW_SECONDS` | لا | طول النافذة، الافتراضي 60 |
| `ALLOWED_ORIGINS` | لا | origins مفصولة بفواصل؛ يظل فارغًا إذا لم توجد واجهة متصفح |

## تجهيز الكوكيز بأمان

صدّر كوكيز جلسة ChatGPT من متصفحك بصيغة Netscape باستخدام أداة موثوقة محليًا، ثم الصق النص في Secret باسم `CHATGPT_COOKIES_NETSCAPE`. لا تضع النص في `README.md` أو ملف `.env` مُلتزم به أو أمر يظهر في سجل الطرفية. إذا انتهت الجلسة أو ظهر login page، صدّر كوكيز جديدة واستبدل Secret ثم أعد تشغيل Space.

## التشغيل المحلي

يتطلب التشغيل Python 3.12 أو أحدث، وDocker أو بيئة Python مناسبة، ومتصفح Chromium الذي يديره Playwright. أنشئ بيئة افتراضية ثم ثبّت المتطلبات:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

انسخ `.env.example` إلى `.env`، عيّن القيم الحقيقية في بيئتك المحلية، ثم شغّل الخادم:

```bash
set -a; . ./.env; set +a
python main.py
```

للتشغيل عبر Docker:

```bash
docker build -t chatgpt-web-api .
docker run --rm -p 7860:7860 \
  -e API_SECRET_KEY="$API_SECRET_KEY" \
  -e CHATGPT_COOKIES_NETSCAPE="$CHATGPT_COOKIES_NETSCAPE" \
  chatgpt-web-api
```

## النشر على Hugging Face Spaces

أنشئ Space من نوع **Docker** أو استخدم Space الحالي `Yousefsg/chatgpt-api`. ارفع محتويات هذا المستودع إلى الفرع `main`، ثم أضف Secrets المذكورة أعلاه. Dockerfile يثبت مكتبات Chromium وXvfb ويشغل التطبيق على المنفذ الذي تتوقعه Spaces، وهو 7860.

بعد اكتمال البناء، تحقق من:

```bash
curl -i https://<username>-<space-name>.hf.space/health
```

ستكون الحالة `200` مع `ready: true` عندما تصبح جلسة المتصفح جاهزة. أثناء بدء Chromium قد تظهر `initializing`. إذا كانت الكوكيز مفقودة أو منتهية فستظهر `503` برسالة عامة، ولن تُكشف قيم Secret.

## واجهة API

كل مسارات `/v1/*` و`/new-chat` تتطلب:

```http
Authorization: Bearer YOUR_API_SECRET_KEY
```

### قائمة النماذج

```bash
curl https://<space>.hf.space/v1/models \
  -H "Authorization: Bearer $API_SECRET_KEY"
```

### Chat Completions

```bash
curl -X POST https://<space>.hf.space/v1/chat/completions \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "أجب باختصار."},
      {"role": "user", "content": "اشرح مفهومًا واحدًا."}
    ]
  }'
```

الرد الناجح هو كائن `chat.completion` يحتوي على `choices[0].message.content`. إذا أُرسلت `tools`، يحاول الخادم تفسير JSON الذي يعيده ChatGPT وإرجاعه داخل `tool_calls`. هذا **محاكاة للتوافق** وليس تنفيذًا تلقائيًا للأداة؛ التطبيق المستدعي هو المسؤول عن تنفيذ الأداة وإرسال نتيجتها لاحقًا.

### Responses

يقبل `/v1/responses` حقل `input` النصي أو قائمة رسائل، ويدعم `instructions` و`tools` بالقدر الذي تستطيع طبقة التحويل الحالية تمثيله.

## البحث الحي

عندما يحتوي طلب المستخدم على عبارات مثل `ابحث في الويب` أو `ابحث في جوجل` أو `ابحث عن` أو `بحث حي`، يضيف الخادم تلقائيًا العبارة التالية قبل البرومبت:

```text
ابحث في الويب بحث حي:
```

وتُضاف البادئة مرة واحدة فقط. يطبق ذلك على `chat.completions` و`responses`، بينما لا تُضاف إلى الأسئلة العادية التي لا تطلب بحثًا خارجيًا. لا يستخدم هذا المسار فحص DOM للصور؛ يعتمد على نص المساعد ونتيجة البحث فقط.

## توليد الصور

للطلبات التي تتضمن `output_type=image` أو prompt واضحًا مثل `generate image`، يفعّل الخادم استخراج الصور من DOM فقط لهذا الطلب. يُقبل العنصر إذا كان يحمل marker مثل `Generated image` أو رابط ChatGPT backend خاصًا بملف مولد. تُرفض favicon وavatar والصور القديمة حتى لا تتحول إلى `images[].data_url` مضللة.

```bash
curl -X POST https://<space>.hf.space/v1/chat/completions \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"generate image of a wise stickman reading a book in a library"}]}'
```

تحقق من أن `images` تحتوي صورة مولدة، وأن `images[].alt` أو `images[].src` يشير إلى asset مولد. إذا لم توجد صورة مولدة، يجب التعامل مع النتيجة كفشل صورة بدل قبول أول صورة صغيرة في الصفحة.

### بدء محادثة جديدة والحالة

```bash
curl -X POST https://<space>.hf.space/new-chat \
  -H "Authorization: Bearer $API_SECRET_KEY"

curl https://<space>.hf.space/health
curl https://<space>.hf.space/status \
  -H "Authorization: Bearer $API_SECRET_KEY"
```

## الاختبارات

تشغّل فحوصات syntax واختبارات الوحدات دون الحاجة إلى جلسة ChatGPT:

```bash
python3 -m compileall -q main.py browser_gateway.py tests
python3 -m unittest discover -s tests -v
```

أما اختبار المتصفح الحقيقي فيظل اختبار تكامل يعتمد على Secret صالح واتصال ChatGPT وDOM غير متغير. يجب وسمه `deferred` عند غياب هذه الشروط بدل اعتباره ناجحًا لمجرد أن Docker بُني.

## حدود معروفة

استخراج DOM مخصص للصور فقط. النص والبحث لا يستدعيان image-count أو image locators، لكنهما يقرآن نص الرد من عناصر المساعد اللازمة للتفاعل مع واجهة ChatGPT. إذا تغيرت selectors الخاصة برسائل المساعد أو الصور، يجب تحديثها واختبار المسارات الثلاثة مجددًا.


الخادم يستخدم جلسة ChatGPT واحدة، لذلك يعالج الطلبات بالتسلسل. لا توجد قاعدة بيانات أو ذاكرة محادثات مستقلة؛ الذاكرة هي حالة جلسة الويب الحالية. لا يوجد streaming في هذه النسخة. كما أن selectors الخاصة بواجهة ChatGPT قد تحتاج تحديثًا إذا تغيرت الصفحة. معدل الاستجابة والاعتمادية يعتمدان على ChatGPT وHF، ولا يوجد ادعاء بتوافر إنتاجي أو SLA.

## المراجع

[1]: https://github.com/CodeMongerrr/cognitive_prosthetic "المشروع المرجعي cognitive_prosthetic"
[2]: https://github.com/ysrg2003/chatgpt-api "مستودع التنفيذ"
[3]: https://huggingface.co/spaces/Yousefsg/chatgpt-api "Hugging Face Space"
