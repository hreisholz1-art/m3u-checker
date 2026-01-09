import os
import shutil
import tempfile
import zipfile
import logging
import asyncio  # ✅ HINZUGEFÜGT
from pathlib import Path
from datetime import datetime

import requests
from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv

# ────────────────────────────────────────────────
#   ЛОГГИРОВАНИЕ
# ────────────────────────────────────────────────

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
#   КОНФИГ
# ────────────────────────────────────────────────

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "hreisholz1-art/m3u-checker"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")
if not GITHUB_TOKEN:
    logger.warning("GITHUB_TOKEN не найден — загрузка в релиз работать не будет")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-very-secure-secret-2026")

COMBINER_SCRIPT = "m3u_combiner_fixed.py"

app = FastAPI(title="M3U Checker Bot 2026")

application: Application = None


# ────────────────────────────────────────────────
#   GitHub Release Upload
# ────────────────────────────────────────────────

def upload_to_github_release(zip_path: Path, original_name: str = "result.zip") -> str | None:
    """Загружает ZIP в релиз дня (тег vГГГГММДД) репозитория hreisholz1-art/m3u-checker"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    api_base = f"https://api.github.com/repos/{REPO}"

    today = datetime.utcnow().strftime("%Y%m%d")
    tag_name = f"v{today}"
    release_name = f"Checked playlists — {today}"

    # 1. Проверяем/создаём релиз дня
    upload_url = None

    try:
        r = requests.get(f"{api_base}/releases/tags/{tag_name}", headers=headers, timeout=10)
        if r.status_code == 200:
            upload_url = r.json()["upload_url"].split("{")[0]
            logger.info(f"Используем существующий релиз {tag_name}")
        else:
            payload = {
                "tag_name": tag_name,
                "target_commitish": "main",
                "name": release_name,
                "body": "Автоматически проверенные плейлисты за день",
                "draft": False,
                "prerelease": False
            }
            r = requests.post(f"{api_base}/releases", json=payload, headers=headers, timeout=15)
            r.raise_for_status()
            upload_url = r.json()["upload_url"].split("{")[0]
            logger.info(f"Создан новый релиз {tag_name}")
    except Exception as e:
        logger.error(f"Ошибка при работе с релизом: {e}")
        return None

    if not upload_url:
        return None

    # 2. Уникальное имя файла
    time_part = datetime.utcnow().strftime("%H%M")
    asset_name = f"m3u_checked_{today}_{time_part}.zip"

    # 3. Загрузка
    try:
        upload_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/zip",
            "Accept": "application/vnd.github.v3+json"
        }

        with open(zip_path, "rb") as f:
            resp = requests.post(
                upload_url,
                headers=upload_headers,
                params={"name": asset_name},
                data=f,
                timeout=60
            )
        resp.raise_for_status()
        download_url = resp.json().get("browser_download_url")
        if download_url:
            logger.info(f"Успешно загружен: {asset_name}")
            return download_url
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки актива: {e}")
        return None


# ────────────────────────────────────────────────
#   TELEGRAM ХЕНДЛЕРЫ
# ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Пришли мне файл плейлиста (.m3u, .m3u8, .txt)\n"
        "Я проверю все потоки и пришлю ссылку на рабочий вариант\n\n"
        "WhatsApp блокирует .m3u? Присылай как .txt — я сам переименую!"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("Пришли пожалуйста файл...")
        return

    original_name = document.file_name or "unnamed"
    lower_name = original_name.lower()

    allowed = ('.m3u', '.m3u8', '.txt', '.text')
    if not any(lower_name.endswith(ext) for ext in allowed):
        await update.message.reply_text(
            "Поддерживаются только файлы:\n.m3u  .m3u8  .txt\n\n"
            "Присылай как .txt если мессенджер блокирует m3u"
        )
        return

    msg = await update.message.reply_text("📥 Скачиваю файл...")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            input_file = tmp_dir / "playlist_from_user.m3u"

            file = await document.get_file()
            await file.download_to_drive(custom_path=str(input_file))

            await msg.edit_text("🔍 Проверяю потоки... (3–20 минут)")

            output_m3u = tmp_dir / "good.m3u"

            # ✅ Проверка наличия FFmpeg
            try:
                ffmpeg_check = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-version",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await ffmpeg_check.communicate()
                if ffmpeg_check.returncode != 0:
                    raise FileNotFoundError("FFmpeg не работает")
            except FileNotFoundError:
                await msg.edit_text(
                    "❌ FFmpeg не установлен на сервере!\n\n"
                    "Свяжитесь с администратором для установки FFmpeg."
                )
                return

            cmd = [
                "python3", COMBINER_SCRIPT,
                str(tmp_dir),
                "-w", "4",
                "-t", "15",
                "-o", str(output_m3u)
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error = stderr.decode(errors='replace')[:500] or "Неизвестная ошибка"
                await msg.edit_text(f"❌ Ошибка обработки:\n\n{error}")
                return

            if not output_m3u.is_file() or output_m3u.stat().st_size < 200:
                await msg.edit_text("❌ Не удалось найти рабочие потоки")
                return

            # ZIP
            zip_name = f"m3u_checked_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            zip_path = tmp_dir / zip_name

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(output_m3u, "good.m3u")

            # Загрузка на GitHub
            await msg.edit_text("📤 Загружаю результат на GitHub...")

            download_url = upload_to_github_release(zip_path, zip_name)

            if download_url:
                await msg.edit_text(
                    "✅ Готово!\n\n"
                    f"Скачать: {download_url}\n\n"
                    f"Релиз дня: https://github.com/{REPO}/releases/tag/v{datetime.utcnow().strftime('%Y%m%d')}",
                    disable_web_page_preview=True
                )
            else:
                await msg.edit_text(
                    "⚠️ Плейлист проверен, но не удалось загрузить на GitHub\n"
                    "Попробуйте позже или напишите @админ"
                )

    except Exception as e:
        logger.exception("Критическая ошибка")
        try:
            await msg.edit_text(f"💥 Что-то сломалось:\n\n{str(e)[:400]}")
        except:
            await update.message.reply_text("💥 Ошибка обработки файла")


# ────────────────────────────────────────────────
#   FASTAPI
# ────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global application
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Бот инициализирован")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(403, "Forbidden")

    try:
        update_dict = await request.json()
        update = Update.de_json(update_dict, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error("Webhook error", exc_info=True)
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)