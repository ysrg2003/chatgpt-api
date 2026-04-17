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
├── main.py               # التطبيق الرئيسي (FastAPI + قائمة الانتظار + Playwright)
├── api_use_on_python.py  # مثال عميل متوافق مع مكتبة openai الرسمية
├── requirements.txt      # متطلبات بايثون
├── Dockerfile            # ملف الحاوية للنشر
├── docker-compose.yml    # للتشغيل المحلي
├── README.md             # التوثيق بالإنجليزية
├── chatgpt_cookies.txt   # ملف الكوكيز لحساب مسجل دخول (مطلوب)
```

---

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

## مثال للاستخدام (عميل بايثون)

> **ملاحظة:** يجب تثبيت المكتبتين requests و openai لتشغيل الأمثلة التالية:
> ```sh
> pip install requests openai
> ```

### مثال استخدام مباشر (متوافق مع openai-python الحديث)
```python
import openai

client = openai.OpenAI(
   api_key="YOUR_API_KEY",
   base_url="http://localhost:7860/v1"
)
response = client.chat.completions.create(
   model="gpt-4o-mini",
   messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### مثال استخدام عبر requests (نمط قائمة الانتظار)
```python
import requests
import time

API_URL = "http://localhost:7860/v1/jobs"
API_KEY = "your_secret_key"

headers = {"Authorization": f"Bearer {API_KEY}"}

# إرسال مهمة
resp = requests.post(API_URL, json={
   "messages": [{"role": "user", "content": "مرحباً!"}],
   "model": "gpt-3.5-turbo",
   "stream": False
}, headers=headers)
job_id = resp.json()["job_id"]

# الاستعلام عن النتيجة
while True:
   r = requests.get(f"http://localhost:7860/v1/jobs/{job_id}", headers=headers)
   data = r.json()
   if data["status"] == "completed":
      print(data["result"])
      break
   elif data["status"] == "failed":
      print("خطأ:", data["error"])
      break
   time.sleep(2)
```

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
   - `API_SECRET_KEY` (القيمة الافتراضية: `gptkey0`، يفضل تعيين قيمة قوية في الإنتاج)
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


