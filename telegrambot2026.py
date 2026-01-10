import os
import tempfile
import zipfile
import logging
import asyncio
import re
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
import json
import base64
import traceback

import requests
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ─────────────── ЛОГИРОВАНИЕ ───────────────
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────── КОНФИГ ───────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-very-secure-secret-2026")
COMBINER_SCRIPT = "m3u_combiner_fixed.py"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")

application: Application = None

# ─────────────── GOOGLE SHEETS ───────────────
COLORS = [
    {"red": 1.0, "green": 0.9, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 0.9, "blue": 1.0},
    {"red": 1.0, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 1.0},
]

def get_color_for_wkn(wkn: str):
    return COLORS[hash(wkn) % len(COLORS)]

def _get_spreadsheet():
    b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
    if not b64:
        raise ValueError("GOOGLE_CREDENTIALS_BASE64 не задан")
    creds_dict = json.loads(base64.b64decode(b64).decode('utf-8'))
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key("1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8")

# ─────────────── TELEGRAM ХЕНДЛЕРЫ ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n"
        "Пришли мне файл плейлиста (.m3u, .m3u8, .txt)\n"
        "Я проверю все потоки и пришлю ZIP с рабочими ссылками."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("Пришли файл.")
        return

    name = (document.file_name or "").lower()
    if not any(name.endswith(ext) for ext in ('.m3u', '.m3u8', '.txt', '.text')):
        await update.message.reply_text("Поддерживаются: .m3u, .m3u8, .txt")
        return

    msg = await update.message.reply_text("📥 Скачиваю...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_path = tmp / "input.m3u"
            await document.get_file().download_to_drive(str(input_path))

            await msg.edit_text("🔍 Проверяю потоки... (3–20 мин)")

            # FFmpeg check
            try:
                proc = await asyncio.create_subprocess_exec("ffmpeg", "-version", stdout=asyncio.subprocess.DEVNULL)
                await proc.communicate()
                if proc.returncode != 0:
                    raise FileNotFoundError
            except FileNotFoundError:
                await msg.edit_text("❌ FFmpeg не установлен")
                return

            output_m3u = tmp / "good.m3u"
            cmd = ["python3", COMBINER_SCRIPT, str(tmp), "-w", "4", "-t", "15", "-o", str(output_m3u)]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()

            if proc.returncode != 0 or not output_m3u.is_file() or output_m3u.stat().st_size < 200:
                await msg.edit_text("❌ Не найдено рабочих потоков")
                return

            # ZIP
            zip_name = f"m3u_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            zip_path = tmp / zip_name
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.write(output_m3u, "good.m3u")

            # Отправка в Telegram
            if zip_path.stat().st_size > 50 * 1024 * 1024:
                await msg.edit_text("❌ Файл >50 МБ — нельзя отправить через бота")
            else:
                await msg.edit_text("📤 Отправляю ZIP...")
                await update.message.reply_document(open(zip_path, "rb"), filename=zip_name)

    except Exception as e:
        logger.exception("Ошибка обработки")
        await update.message.reply_text("💥 Ошибка. Попробуйте позже.")

# ─────────────── СКРЫТЫЕ КОМАНДЫ ───────────────
async def handle_hidden_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # /mysecret
    if text == "/mysecret":
        await update.message.reply_text(
            "🔐 Скрытые команды:\n\n"
            "• <code>wkn123456 45.50euro</code> — добавить дивиденд\n"
            "• <code>del02.06</code> — удалить записи за 2 июня\n"
            "• <code>new27</code> — создать лист на 2027 год",
            parse_mode="HTML"
        )
        return

    # new27
    if match := re.fullmatch(r"new(\d{2})", text, re.IGNORECASE):
        year = f"20{match.group(1)}"
        try:
            sh = _get_spreadsheet()
            sh.duplicate_sheet(sh.sheet1.id, insert_sheet_index=1, new_sheet_name=year)
            sheet = sh.worksheet(year)
            sheet.clear()
            sheet.update("A1:D2", [
                ["Дата", "WKN", "Акция", "Сумма (€)"],
                ["", "", "", "=SUM(D3:D1000)"]
            ])
            await update.message.reply_text(f"🆕 Лист {year} создан")
        except Exception as e:
            logger.error(f"new error: {e}")
        return

    # del02.06
    if match := re.fullmatch(r"del(\d{2})\.(\d{2})", text, re.IGNORECASE):
        day, month = match.groups()
        target = f"{datetime.now().year}-{month}-{day}"
        try:
            sheet = _get_spreadsheet().sheet1
            rows = sheet.get_all_values()
            to_del = [i+1 for i, r in enumerate(rows[2:], start=3) if r and r[0] == target]
            for i in sorted(to_del, reverse=True):
                sheet.delete_rows(i)
            last = max(3, len(sheet.get_all_values()))
            sheet.update("D2", f"=SUM(D3:D{last})")
            await update.message.reply_text(f"🗑️ Удалено {len(to_del)} записей за {day}.{month}")
        except Exception as e:
            logger.error(f"del error: {e}")
        return

    # wkn123456 50euro
    if match := re.fullmatch(r"wkn([a-zA-Z0-9]+)\s+(\d+\.?\d*)\s*euro", text, re.IGNORECASE):
        wkn, amount = match.groups()
        amount = float(amount)
        try:
            sheet = _get_spreadsheet().sheet1
            next_row = len(sheet.get_all_values()) + 1
            if next_row < 3:
                next_row = 3
            sheet.update(f"A{next_row}", [[
                datetime.now().strftime("%Y-%m-%d"),
                wkn,
                f"WKN{wkn}",
                amount
            ]])
            color = get_color_for_wkn(wkn)
            sheet.format(f"A{next_row}:D{next_row}", {"backgroundColor": color})
            sheet.update("D2", f"=SUM(D3:D{next_row})")
            await update.message.reply_text("✅ Готово!")
        except Exception as e:
            logger.error(f"wkn error: {e}")
        return

# ─────────────── /divlog — ДИАГНОСТИКА ───────────────
async def divlog_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        if not b64:
            await update.message.reply_text("❌ GOOGLE_CREDENTIALS_BASE64 не задан")
            return

        creds_dict = json.loads(base64.b64decode(b64).decode('utf-8'))
        if "client_email" not in creds_dict:
            await update.message.reply_text("❌ Неверный формат credentials.json")
            return

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8").sheet1
        value = sheet.acell("A1").value or "пусто"

        await update.message.reply_text(
            f"✅ Подключение успешно!\n"
            f"Email: {creds_dict['client_email']}\n"
            f"A1: {value}"
        )

    except Exception as e:
        error_detail = traceback.format_exc()
        msg = f"❌ Ошибка:\n\n{error_detail[-3900:]}"
        await update.message.reply_text(msg)

# ─────────────── FASTAPI ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    await application.initialize()
    await application.start()
    
    # Регистрация хендлеров
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mysecret", handle_hidden_commands))
    application.add_handler(CommandHandler("divlog", divlog_debug))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hidden_commands))
    
    logger.info("✅ Бот запущен")
    yield
    await application.stop()
    await application.shutdown()

app = FastAPI(title="M3U Checker Bot 2026", lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(403)
    try:
        update = Update.de_json(await request.json(), application.bot)
        await application.update_queue.put(update)
        return {"ok": True}
    except Exception as e:
        logger.error("Webhook error", exc_info=True)
        raise HTTPException(500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
