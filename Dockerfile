FROM python:3.11-slim

# Установка системных зависимостей (совместимо с Debian trixie)
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

WORKDIR /app

# Установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Проверка установки (опционально)
RUN ffmpeg -version && tesseract --version

EXPOSE 8000

# Запуск бота
CMD ["python", "telegrambot2026.py"]
