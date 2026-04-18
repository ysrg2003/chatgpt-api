# ---
# title: MSE AI API (Unofficial OpenAI/ChatGPT API)
# emoji: 🤖
# colorFrom: blue
# colorTo: indigo
# sdk: docker
# app_file: main.py
# pinned: false
# license: mit
# description: >-
#   Unofficial OpenAI/ChatGPT-compatible API server with browser automation and job queue for long-running tasks. Supports FastAPI, Playwright, and Docker. Ready for Hugging Face Spaces.
# ---
# واجهة برمجة تطبيقات الذكاء الاصطناعي (MSE AI API)

واجهة برمجة تطبيقات غير رسمية متوافقة مع OpenAI API وChatGPT API، يمكنك استخدامها بنفس طريقة استخدام مكتبة openai الرسمية أو أي عميل متوافق مع بروتوكول OpenAI، لكنها تعمل محليًا أو على سيرفرك الخاص وتعتمد على FastAPI وPlaywright في الخلفية. تدعم المهام الطويلة عبر نظام قائمة الانتظار (Job Queue) وتسمح بأتمتة المتصفح وتنفيذ مهام الذكاء الاصطناعي بشكل مرن وآمن.

## ما هو هذا المشروع؟

هذا المشروع عبارة عن واجهة برمجة تطبيقات (API) متقدمة مبنية على FastAPI، تتيح لك تنفيذ مهام الذكاء الاصطناعي (مثل الدردشة التفاعلية) وأتمتة المتصفح باستخدام Playwright. تم تصميمه ليعمل بكفاءة على منصة Hugging Face Spaces (نوع Docker)، مع دعم كامل للمهام الطويلة التي تتجاوز حدود المهلة الزمنية الافتراضية (60 ثانية) عبر نمط قائمة الانتظار (Job Queue).

## ما هي الاستفادة منه؟
- **بديل ل openai api (chatgpt)** 
- **تشغيل نماذج الذكاء الاصطناعي عبر الإنترنت أو محليًا** مع إمكانية أتمتة المتصفح (مثل استخراج البيانات، التفاعل مع صفحات الويب، إلخ).
- **دعم المهام الطويلة** بدون انقطاع أو أخطاء مهلة زمنية، مما يجعله مناسبًا للمهام المعقدة أو البطيئة.
- **واجهة برمجة تطبيقات آمنة** يمكن استخدامها من أي لغة برمجة أو نظام خارجي.
- **جاهز للنشر على Hugging Face Spaces** أو أي بيئة تعتمد على Docker.
- **مرونة في الاستخدام**: يمكن استخدامه كخدمة خلفية (Backend) لأي تطبيق أو نظام ذكاء اصطناعي.

---

## المميزات الرئيسية

- FastAPI: إطار عمل سريع وحديث لبناء واجهات برمجة التطبيقات في بايثون.
- Playwright: أتمتة متقدمة للمتصفح (Chromium) بدون واجهة رسومية.
- قائمة انتظار للمهام (Job Queue): تنفيذ المهام الطويلة في الخلفية مع إمكانية الاستعلام عن حالتها.
   حتى عند استخدام مكتبة openai الرسمية أو أي عميل متوافق مع OpenAI API (مثل /v1/chat/completions)، يقوم السيرفر داخليًا بتحويل الطلب إلى نظام Job Queue تلقائيًا. هذا يسمح بتجاوز مهلة 60 ثانية المفروضة من Hugging Face Spaces أو أي reverse proxy، ويضمن عدم انقطاع المهام الطويلة.
   - ThreadPoolExecutor: إدارة وتنفيذ المهام في الخلفية بكفاءة.
   - حماية عبر متغير بيئي (API_KEY).
   - جاهز للعمل داخل Docker وHugging Face Spaces.
- مثال عميل (test.py) يوضح طريقة الاستخدام.

---

## ملف الكوكيز (chatgpt_cookies.txt)

يجب عليك وضع ملف الكوكيز (`chatgpt_cookies.txt`) يحتوي على كوكيز صالحة لحساب ChatGPT مسجل عليه دخول.  
يمكنك استخراج الكوكيز من متصفحك بعد تسجيل الدخول إلى chatgpt.com.

**أسهل طريقة:**  
استخدم إضافة كروم [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)  
بعد تثبيت الإضافة، قم بتصدير الكوكيز واحفظ الملف بنفس الاسم الحالي:  
`chatgpt_cookies.txt`  
ثم ضع الملف في مجلد المشروع بجانب `main.py`.

- بدون ملف الكوكيز لن يستطيع السيرفر الوصول إلى حسابك في ChatGPT ولن يعمل بشكل صحيح.
- يتم تحميل الكوكيز تلقائيًا عند بدء السيرفر.

---

## هيكل الملفات

```
.
├── main.py               # التطبيق الرئيسي: FastAPI + Job Queue + تكامل Playwright (تشغيل السيرفر)
├── api_use_on_python.py  # مثال عميل يستخدم مكتبة `openai` (مباشر عبر /v1/chat/completions)
├── test.py               # مثال عميل يستخدم /v1/jobs (نمط قائمة الانتظار؛ مناسب للمهام الطويلة)
├── requirements.txt      # متطلبات Python للسيرفر والأمثلة
├── Dockerfile            # إعداد الحاوية: يثبت Google Chrome ويدعو `playwright install`
├── docker-compose.yml    # مثال لتشغيل الحاويات محليًا
├── chatgpt_cookies.txt   # ملف الكوكيز المطلوب لحساب ChatGPT (يستخدمه Playwright)
├── keepalive.py          # سكربت مساعدة للحفاظ على جلسة المتصفح (اختياري)

```

---

ملاحظات قصيرة:

- أمثلة الاستخدام موجودة كملفات (`api_use_on_python.py`, `test.py`) داخل المستودع — لا حاجة لنسخ الشيفرات داخل هذا الملف.

- لتشغيل أمثلة العملاء فقط:
  ```sh
  pip install requests openai
  ```

- لتثبيت متطلبات السيرفر (شاملة):
  ```sh
  pip install -r requirements.txt
  ```

- ملاحظة Playwright وChrome:
  - `main.py` ينشئ سياق Playwright باستخدام `channel="chrome"` وملف ملف التعريف المستمر `chrome-profile-real`.
  - إذا كان Google Chrome مثبتًا على النظام، قد يُستخدم مباشرة عبر `channel="chrome"`، لكن يُنصح دائمًا بتثبيت متصفحات Playwright الموصى بها:
    ```sh
    playwright install chromium
    ```
  - يحتوي `Dockerfile` على خطوات لتثبيت Google Chrome وينفّذ `playwright install chromium` داخل الصورة، لذلك داخل الحاوية لا حاجة لإجراءات إضافية.

## متى تستخدم api_use_on_python.py ومتى تستخدم test.py؟

### api_use_on_python.py
- يستخدم مكتبة openai الرسمية مع ‎/v1/chat/completions‎.
- مناسب للمهام السريعة أو عند العمل محليًا أو على سيرفر بدون مهلة زمنية قصيرة.
- إذا كان السيرفر يدعم تحويل الطلبات داخليًا إلى job queue، يمكنه معالجة المهام الطويلة تلقائيًا، لكن إذا كان هناك مهلة زمنية من reverse proxy أو Hugging Face Spaces قد ينقطع الاتصال من جهة العميل حتى لو استمر السيرفر في المعالجة.

### test.py
- يستخدم requests ويرسل الطلبات إلى ‎/v1/jobs‎ (نظام قائمة الانتظار).
- مناسب للمهام الطويلة أو عند العمل على بيئة معرضة لمهلة زمنية قصيرة (مثل Hugging Face Spaces).
- يضمن عدم انقطاع الاتصال حتى لو استغرقت المهمة وقتًا طويلًا، حيث يتم الاستعلام عن النتيجة بشكل متكرر حتى تكتمل.

### نصيحة عامة
- إذا كنت غير متأكد من بيئة التشغيل أو تتوقع مهام طويلة، استخدم ‎test.py‎ أو أي عميل يتعامل مع ‎/v1/jobs‎ مباشرة.
- إذا كنت تعمل محليًا أو على سيرفر بدون مهلة زمنية، يمكنك استخدام ‎api_use_on_python.py‎ أو أي عميل متوافق مع openai.


## نقاط النهاية (Endpoints)

- ### 1. إرسال مهمة جديدة
- **POST /v1/jobs**
- **الرأس:** `Authorization: Bearer <API_KEY>`
- **الجسم:**
  ```json
  {
    "messages": [
      {"role": "user", "content": "..."},
      ...
    ],
    "model": "<model_name>",
    "stream": false
  }
  ```
- **الاستجابة:**
  ```json
  { "job_id": "<job_id>" }
  ```

- ### 2. الاستعلام عن حالة/نتيجة المهمة
- **GET /v1/jobs/{job_id}**
- **الرأس:** `Authorization: Bearer <API_KEY>`
- **الاستجابة:**
  - **قيد التنفيذ:** `{ "status": "pending" }`
  - **مكتملة:** `{ "status": "completed", "result": { ... } }`
  - **فشل:** `{ "status": "failed", "error": "..." }`

### 3. (اختياري) إكمال الدردشة مباشرة
- **POST /v1/chat/completions**
- **ملاحظة:** قد تتعرض لمهلة زمنية (Timeout) على Hugging Face Spaces. استخدم `/v1/jobs` للمهام الطويلة.

---

## أمثلة الاستخدام (ملفات)

الملفات `api_use_on_python.py` و `test.py` تحتويان أمثلة جاهزة للاستخدام — لا داعي لنسخ الشيفرات داخل هذا الملف، شغّل الملفات مباشرة لتجربة الطلبات.

- **مكتبات مطلوبة للأمثلة:** `requests`, `openai`.
  - تثبيت سريع للأمثلة فقط:
    ```sh
    pip install requests openai
    ```

- **تثبيت المتطلبات الكاملة (السيرفر + أمثلة):**
  ```sh
  pip install -r requirements.txt
  ```

**ملاحظة مهمة عن Playwright والمتصفح:**
- يستخدم `main.py` Playwright ويحاول تشغيل متصفح النظام عبر `channel="chrome"` عند إنشاء السياق (`launch_persistent_context`). هذا يعني أنه إذا كان Google Chrome مثبتًا على النظام، فقد يتم استخدامه مباشرة.
- مع ذلك، لضمان توافق أفضل خاصة في بيئات جديدة أو داخل حاويات Docker، ننصح بتشغيل الأمر التالي لتثبيت متصفحات Playwright الموصى بها:
  ```sh
  playwright install chromium
  ```
- يحتوي `Dockerfile` أيضاً على خطوات لتثبيت Google Chrome وينفّذ `playwright install chromium` لذلك عند تشغيل الحاوية لا حاجة لإجراءات إضافية.

---

## خطوات التشغيل والتثبيت

### محليًا
1. **إنشاء بيئة افتراضية:**
   - ويندوز: `python -m venv .venv && .venv\Scripts\activate`
   - لينكس/ماك: `python -m venv .venv && source .venv/bin/activate`
2. **تثبيت المتطلبات:**
   ```sh
   pip install -r requirements.txt
   playwright install chromium
   ```
3. **تشغيل التطبيق:**
   ```sh
   python main.py
   # أو
   uvicorn main:app --host 0.0.0.0 --port 7860
   ```

### عبر Docker (موصى به لـ Hugging Face Spaces)
1. **بناء صورة Docker:**
   ```sh
   docker build -t mse_ai_api .
   ```
2. **تشغيل عبر Docker Compose:**
   ```sh
   docker-compose up --build -d
   ```
3. **تعيين متغير البيئة:**
   - `API_KEY` (القيمة الافتراضية: `gptkey0`، يفضل تعيين قيمة قوية في الإنتاج)
4. **تأكد من فتح المنفذ:**
   - المنفذ الافتراضي `7860`

### على Hugging Face Spaces (نوع Docker)
1. **أنشئ Space جديد** (اختر Docker كبيئة تشغيل).
2. **ارفع جميع ملفات المشروع** (`main.py`, `requirements.txt`, `Dockerfile`, ...).
3. **عيّن متغير البيئة `API_KEY`** من إعدادات الأسرار (Secrets).
4. **انشر المشروع.**
5. **استخدم الواجهة البرمجية** عبر الرابط: `https://<your-space-id>.hf.space/v1/jobs`

---

## المتغيرات البيئية
- `API_KEY`: مفتاح سري لحماية الواجهة البرمجية (مطلوب لجميع الطلبات).

---

## الأمان
- استخدم دومًا مفتاح سري قوي في `API_KEY`.
- لا تفتح الواجهة البرمجية للعامة بدون حماية.
- راجع Dockerfile قبل النشر النهائي.

---

## حل المشاكل الشائعة
- **مهلة زمنية:** استخدم نقاط `/v1/jobs` للمهام الطويلة.
- **مشاكل Playwright:** تأكد من تنفيذ `playwright install chromium`.
- **مشاكل في تشغيل المتصفح:** تحقق من السجلات (logs) لأي أخطاء عند بدء التشغيل.
- **مشاكل في المنفذ:** تأكد أن المنفذ `7860` مفتوح وموجه بشكل صحيح.


