# Используем Python 3.11 slim (стабильная версия, совместимая с Debian trixie)
FROM python:3.11-slim

# Устанавливаем системные зависимости — без устаревшего libgl1-mesa-glx
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости и устанавливаем Python-пакеты
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Проверяем установку FFmpeg и Tesseract (опционально, но полезно для отладки)
RUN ffmpeg -version && tesseract --version

# Порт, который Render будет использовать (через переменную окружения PORT)
EXPOSE 8000

# Запуск бота
CMD ["python", "telegrambot2026.py"]
