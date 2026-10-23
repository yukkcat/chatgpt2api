FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./
# 只安装完整 Chromium（新版无头模式），headless shell 过不了 Cloudflare
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps --no-shell chromium \
    && rm -rf /var/lib/apt/lists/*

COPY app.py vm.js ./

EXPOSE 35780
CMD ["python", "app.py"]
