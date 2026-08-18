FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CHATGPT_HEADLESS=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libx11-xcb1 libxcb1 libxshmfence1 xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium \
    && playwright install-deps chromium

COPY . .

EXPOSE 7860

CMD ["xvfb-run", "-a", "--server-args=-screen 0 1440x900x24 -nolisten tcp", "python", "main.py"]
