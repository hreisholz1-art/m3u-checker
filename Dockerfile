FROM python:3.11-slim

# Установка FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

EXPOSE 10000

CMD ["uvicorn", "telegrambot2026:app", "--host", "0.0.0.0", "--port", "10000"]
