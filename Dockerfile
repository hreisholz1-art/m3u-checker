# Используем Python 3.11 slim базу
FROM python:3.11-slim

# Устанавливаем системные зависимости для FFmpeg, OpenCV и Tesseract
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Проверяем что FFmpeg и Tesseract установлены
RUN ffmpeg -version && tesseract --version

# Expose порт (Render использует переменную PORT)
EXPOSE 8000

# Запуск бота
CMD ["python", "telegrambot2026.py"]