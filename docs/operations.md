# تشغيل ونشر `chatgpt-api`

## الهدف

الخادم هو طبقة FastAPI متوافقة جزئيًا مع OpenAI، وتستخدم جلسة Playwright مستمرة داخل ChatGPT. يدعم النص، البحث الحي، واسترجاع الصور المولدة من عناصر `<img>` بعد اكتمال التوليد.

## التشغيل المحلي

من جذر المشروع:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
playwright install --with-deps chromium
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 7860
```

النتيجة المتوقعة:

```text
Uvicorn running on http://0.0.0.0:7860
```

إذا فشل تثبيت Chromium، نفّذ أمر تثبيت المتصفح مرة أخرى داخل البيئة نفسها. لا تشغّل الخادم قبل وضع Secrets المطلوبة.

## فحص الصحة

لا يحتاج `/health` إلى مفتاح:

```bash
curl -i http://127.0.0.1:7860/health
```

القيمة الناجحة هي HTTP 200 مع `ready: true`. إذا كانت `ready: false` مع `initializing`، انتظر تجهيز المتصفح. إذا كانت 503، راجع رسالة `error` ولا تعيد الطلبات بلا تغيير في الإعداد.

## اختبار نص

```bash
curl -sS -X POST http://127.0.0.1:7860/v1/chat/completions \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"قل فقط: نجح اختبار النص"}]}'
```

النجاح يتطلب HTTP 200 ووجود `choices[0].message.content`.

## اختبار البحث الحي

أي طلب يتضمن مؤشرات مثل `ابحث في الويب` أو `ابحث في جوجل` أو `ابحث عن` أو `web search` يضيف الخادم تلقائيًا العبارة:

```text
ابحث في الويب بحث حي:
```

مثال:

```bash
curl -sS -X POST http://127.0.0.1:7860/v1/chat/completions \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ابحث عن اخر موديل anthropic ai"}]}'
```

لا تُعتبر النتيجة مثبتة بمجرد HTTP 200؛ افحص أن الرد يذكر البحث الحي والمصادر أو المعلومات الحديثة المطلوبة.

## اختبار توليد الصور

أرسل prompt توليد صورة بالطريقة نفسها:

```bash
curl -sS -X POST http://127.0.0.1:7860/v1/chat/completions \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"generate image of wise steakman read book in libary"}]}' \
  > image-response.json
```

ابحث عن `images[0].data_url`. قد يحتوي الرد أيضًا على `images[0].src`، لكن هذا الرابط قد يتطلب Cookies الجلسة. العميل الموثوق يجب أن يستخدم `data_url` أو يقوم بالتنزيل من داخل جلسة مصادق عليها. لا تعتمد على طلب HTTP خارجي عارٍ إلى رابط `chatgpt.com/backend-api` لأن ذلك قد يعيد 403.

## GitHub Actions

يحتوي المستودع على Workflows يدوية:

| Workflow | الوظيفة | Secret المطلوب | Artifact |
|---|---|---|---|
| `test-image.yml` | اختبار توليد صورة | `API_SECRET_KEY` | `generated-image` |
| `test-text-search.yml` | اختبار النص والبحث الحي | `API_SECRET_KEY` | `text-search-results` |

أضف `API_SECRET_KEY` من صفحة **Settings → Secrets and variables → Actions**. لا تستخدم GitHub Variables لهذا المفتاح. شغّل Workflow من **Actions → Run workflow**، وراجع exit code وartifact، لا حالة صفحة التشغيل وحدها.

## النشر إلى Hugging Face Docker Space

يحتاج Space إلى metadata Docker في أعلى README وDockerfile يشغل Uvicorn على المنفذ 7860. بعد دفع commit:

1. راقب runtime في صفحة Space حتى ينتقل من `BUILDING` إلى `RUNNING`.
2. افحص `https://YOUR_SPACE.hf.space/health`.
3. اختبر `/v1/models` بمفتاح API.
4. نفّذ اختبارًا محدودًا واحدًا للنص، ثم اختبارًا للبحث، ثم اختبار الصورة.

إذا بقي runtime في `APP_STARTING`، اقرأ build/run logs الرسمية. لا ترفع Secrets داخل الملفات لتشخيص المشكلة.

## التزامن والحدود

يستخدم `BrowserGateway` قفلًا واحدًا لكل جلسة، لذلك تُسلسل الطلبات التي تستخدم المتصفح نفسه. يفرض الخادم حدًا افتراضيًا قدره 20 طلبًا لكل 60 ثانية لكل عنوان عميل. زمن الطلب الافتراضي 210 ثانية، وقد تحتاج الصور إلى وقت أطول من النص.

## الاسترداد والرجوع

قبل نشر تغيير، شغّل:

```bash
python3 -m compileall -q main.py browser_gateway.py tests
API_SECRET_KEY=test-secret python3 -m unittest discover -s tests -v
```

إذا فشل الإصدار المنشور، ارجع إلى آخر commit معروف عبر Git أو أعد تشغيل Space على commit سابق. لا تحذف سجلات التشخيص قبل حفظ HTTP status وruntime stage وcommit SHA.

## التنظيف

احذف ملفات التصدير المحلية لـCookies، وامنع `.env` وملفات الردود والصور من Git. بعد اختبار GitHub Actions، احذف artifacts التي تحتوي بيانات حساسة أو اضبط مدة الاحتفاظ المناسبة. دوّر `API_SECRET_KEY` وCookies فور تعرضهما.
