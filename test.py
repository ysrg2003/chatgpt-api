import time
import requests


# ضع هنا نفس المفتاح الذي استخدمته في متغير البيئة أو في main.py
API_KEY = "gptkey0"
base_url = "https://yousefsg-chatgpt-api.hf.space"
headers = {
    # يمكنك استخدام Bearer أو فقط المفتاح مباشرة حسب ما يدعمه السيرفر
    "Authorization": API_KEY,
    "Content-Type": "application/json; charset=utf-8"
}

payload = {
    "messages": [
        {"role": "user", "content": "what is the model u are using?"}
    ]
}

create_job = requests.post(f"{base_url}/v1/jobs", json=payload, headers=headers)
create_job.raise_for_status()
job_id = create_job.json()["job_id"]

while True:
    status = requests.get(f"{base_url}/v1/jobs/{job_id}", headers=headers)
    status.raise_for_status()
    data = status.json()

    if data["status"] == "done":
        reply = data["response"]["choices"][0]["message"]["content"]
        print(reply)
        break

    if data["status"] == "error":
        raise RuntimeError(data["error"])

    time.sleep(3)