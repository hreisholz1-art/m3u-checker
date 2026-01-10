FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN ffmpeg -version && tesseract --version

EXPOSE 8000
CMD ["python", "telegrambot2026.py"]
