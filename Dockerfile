FROM python:3.11-slim

WORKDIR /app

# لا نحتاج dependencies خارجية
COPY server.py .

# Render يستخدم متغير PORT تلقائياً
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "server.py"]
