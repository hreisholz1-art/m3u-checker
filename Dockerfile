FROM python:3.11-slim

# Nur FFmpeg für M3U processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

EXPOSE 10000

CMD ["uvicorn", "telegrambot2026:app", "--host", "0.0.0.0", "--port", "10000"]
