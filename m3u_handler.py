"""
m3u_handler.py - ТОЛЬКО обработка M3U файлов
Никакой финансовой логики!
"""
import os
import shutil
import zipfile
import asyncio
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

COMBINER_SCRIPT = "m3u_combiner_fixed.py"
ALLOWED_EXTENSIONS = ['.m3u', '.m3u8', '.txt']

async def process_m3u_document(update, context):
    """
    Обрабатывает M3U файлы:
    1. Скачивает документ
    2. Запускает внешний combiner
    3. Упаковывает в ZIP
    4. Отправляет пользователю
    """
    doc = update.message.document
    file_name = doc.file_name or "input.m3u"
    
    # Валидация расширения
    if not any(file_name.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        await update.message.reply_text(
            f"❌ Поддерживаются только файлы: {', '.join(ALLOWED_EXTENSIONS)}"
        )
        return
    
    # Создание временной директории
    uid = update.effective_user.id
    timestamp = datetime.now().strftime("%f")
    temp_dir = f"temp_{uid}_{timestamp}"
    os.makedirs(temp_dir, exist_ok=True)
    
    status_msg = None
    
    try:
        status_msg = await update.message.reply_text("⏳ M3U обрабатывается...")
        
        # Скачивание файла
        tg_file = await doc.get_file()
        input_path = os.path.join(temp_dir, file_name)
        await tg_file.download_to_drive(input_path)
        
        logger.info(f"Downloaded: {file_name} ({os.path.getsize(input_path)} bytes)")
        
        # Запуск внешнего combiner
        output_m3u = os.path.join(temp_dir, "output.m3u")
        success = await asyncio.to_thread(_run_combiner, temp_dir, output_m3u)
        
        if not success:
            await status_msg.edit_text("❌ Ошибка обработки M3U файла")
            return
        
        # Создание ZIP архива
        zip_filename = f"m3u_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(output_m3u, arcname="output.m3u")
        
        logger.info(f"Created ZIP: {zip_filename} ({os.path.getsize(zip_path)} bytes)")
        
        # Отправка результата
        with open(zip_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=zip_filename,
                caption="✅ M3U обработан успешно"
            )
        
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"M3U processing error: {e}", exc_info=True)
        if status_msg:
            await status_msg.edit_text("❌ Внутренняя ошибка при обработке")
    
    finally:
        # Очистка временных файлов
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"Cleaned up: {temp_dir}")

def _run_combiner(input_dir: str, output_file: str) -> bool:
    """
    Запускает внешний m3u_combiner_fixed.py скрипт.
    Возвращает True если успешно.
    """
    cmd = [
        "python3", COMBINER_SCRIPT,
        input_dir,
        "-w", "4",      # 4 worker threads
        "-t", "15",     # 15 sec timeout
        "-o", output_file
    ]
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            timeout=300,  # 5 минут максимум
            capture_output=True,
            text=True
        )
        
        logger.info(f"Combiner output: {result.stdout}")
        
        # Проверка результата
        if not os.path.exists(output_file):
            logger.error("Output file not created")
            return False
        
        if os.path.getsize(output_file) < 200:
            logger.error(f"Output file too small: {os.path.getsize(output_file)} bytes")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Combiner timeout (5 min)")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Combiner failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Combiner error: {e}")
        return False
