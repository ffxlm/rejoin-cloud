# Backend image — Rejoin (production)
# build:  docker compose -f deploy/docker-compose.yml build
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# dependency ก่อน (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# โค้ด
COPY skeleton ./skeleton

# ไม่ต้องมีไฟล์ในเครื่อง — ทุกอย่างมาจาก env
EXPOSE 8000

# healthcheck (ใช้โดย compose)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "skeleton.backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
