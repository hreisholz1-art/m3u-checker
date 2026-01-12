import logging
from aiogram import types
import os
import subprocess

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_m3u_document(message: types.Message):
    if not message.document.file_name.endswith(('.m3u', '.m3u8', '.txt')):
        await message.answer("❌ Поддерживаются только M3U/M3U8/TXT файлы.")
        return

    # Сохранение файла
    file_id = message.document.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    downloaded_file = await message.bot.download_file(file_path)

    # Путь для сохранения
    save_path = f"temp_{message.document.file_name}"
    with open(save_path, "wb") as f:
        f.write(downloaded_file.read())

    logger.info(f"Файл {message.document.file_name} сохранён как {save_path}")
    await message.answer("📄 Файл принят. Отправьте команду /combine для объединения.")
