# التكامل من مشروع آخر

## حد التكامل

يستخدم المشروع المستهلك حدًا HTTP مع خدمة `chatgpt-api` المنشورة على Hugging Face. هذا الحد يفصل جلسة المتصفح وCookies عن مشروع الراوتر؛ لذلك لا تُنسخ Cookies إلى المشروع المستهلك، ولا يحتاج الراوتر إلى تشغيل Chromium محليًا.

## المتطلبات

يحتاج المشروع المستهلك إلى عنوان Space و`API_SECRET_KEY` محفوظ في مدير أسراره. يحتاج الطلب إلى ترويسة:

```http
Authorization: Bearer YOUR_API_SECRET_KEY
Content-Type: application/json
```

لا تُضع القيمة الحقيقية في URL أو query string أو السجل.

## عقد النص

```http
POST /v1/chat/completions
```

مثال آمن:

```python
import os
import requests

response = requests.post(
    os.environ["CHATGPT_API_BASE_URL"] + "/v1/chat/completions",
    headers={
        "Authorization": "Bearer " + os.environ["CHATGPT_API_SECRET_KEY"],
        "Content-Type": "application/json",
    },
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "قل فقط: نجح الاختبار"}],
    },
    timeout=240,
)
response.raise_for_status()
payload = response.json()
text = payload["choices"][0]["message"]["content"]
```

النتيجة الناجحة تحتوي `choices[0].message.content` و`usage`. قد يحتوي الرد على `images: []` في طلبات النص.

## عقد البحث الحي

لا يحتاج المستهلك إلى بناء أداة بحث منفصلة. عندما يتضمن نص المستخدم مؤشرات البحث، يضيف الخادم العبارة `ابحث في الويب بحث حي:` قبل البرومبت. ينبغي للمستهلك أن يرسل نص المستخدم كما هو، دون إضافة البادئة بنفسه، حتى لا تتكرر.

## عقد الصورة

يستخدم المستهلك الطلب نفسه مع prompt توليد صورة. النتيجة الناجحة تحتوي عنصرًا واحدًا أو أكثر في `images`. الحقول المهمة:

| الحقل | الاستخدام |
|---|---|
| `images[].data_url` | أفضل مسار للتنزيل مباشرة بعد الرد |
| `images[].src` | رابط جلسة قد يحتاج Cookies؛ لا تطلبه خارج جلسة المتصفح دون مصادقة |
| `images[].alt` | وصف مساعد إن توفر |
| `choices[0].message.content` | نص مرفق إن أعاده ChatGPT |

مثال تنزيل `data_url`:

```python
import base64
import re

item = payload["images"][0]
header, encoded = item["data_url"].split(",", 1)
match = re.search(r"image/([a-z0-9.+-]+)", header)
extension = match.group(1) if match else "png"
with open("generated-image." + extension, "wb") as handle:
    handle.write(base64.b64decode(encoded))
```

## المهلات وإعادة المحاولة

النص عادة أسرع من الصورة. استخدم مهلة لا تقل عن 240 ثانية لطلبات الصورة، وطبّق إعادة محاولة محدودة على أخطاء الشبكة و5xx فقط. لا تعِد المحاولة بلا نهاية ولا تعِد طلبًا بعد 401/403 قبل تدوير Secret أو إصلاح الإعداد.

## health check

```bash
curl -fsS "$CHATGPT_API_BASE_URL/health"
```

النجاح يعني HTTP 200 و`ready: true`. إذا أُعيد 503، أوقف الاختبار الحي وراجع حالة Space وSecret وCookies.

## التراجع والتنظيف

احتفظ بعنوان Space ومتغيري البيئة خارج الكود. لتبديل النسخة، غيّر `CHATGPT_API_BASE_URL` إلى Space بديل أو عطّل provider في config. احذف ملفات الردود والصور الناتجة من بيئة CI إذا كانت تحتوي على بيانات خاصة، ودوّر Secret وCookies عند التعرض.
