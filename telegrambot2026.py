import os
import tempfile
import zipfile
import logging
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
import json
import base64
import traceback
import re
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
import requests

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Excel
from openpyxl import Workbook
from openpyxl.styles import PatternFill

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
DB_PATH = Path("dividends.db")

# ─────────────── БАЗА ДАННЫХ ───────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dividends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            wkn TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            logo_url TEXT,
            year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS wkn_lookup (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            logo_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def load_wkn_json():
    if not Path("wkn.json.txt").exists():
        return
    try:
        with open("wkn.json.txt", "r", encoding="utf-8") as f:
            data = json.load(f)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for item in data:
            name = item.get("name", "")
            logo = item.get("logo_url", "").strip()
            wkn = item.get("wkn", "").strip().upper()
            isin = item.get("isin", "").strip().upper()
            if wkn:
                c.execute("INSERT OR REPLACE INTO wkn_lookup (code, name, logo_url) VALUES (?, ?, ?)", (wkn, name, logo))
            if isin:
                c.execute("INSERT OR REPLACE INTO wkn_lookup (code, name, logo_url) VALUES (?, ?, ?)", (isin, name, logo))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка загрузки wkn.json.txt: {e}")

def get_wkn_info(code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, logo_url FROM wkn_lookup WHERE code = ?", (code.upper(),))
    result = c.fetchone()
    conn.close()
    if result:
        return {"name": result[0], "logo": result[1]}
    return None

def add_dividend_to_db(date: str, wkn: str, name: str, amount: float, logo_url: str = "", year: int = None):
    if year is None:
        year = datetime.now().year
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO dividends (date, wkn, name, amount, logo_url, year) VALUES (?, ?, ?, ?, ?, ?)",
              (date, wkn, name, amount, logo_url, year))
    conn.commit()
    conn.close()

def delete_dividends_by_date(date: str, year: int = None):
    if year is None:
        year = datetime.now().year
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM dividends WHERE date = ? AND year = ?", (date, year))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

def generate_excel(year: int = None):
    if year is None:
        year = datetime.now().year
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT date, wkn, name, amount FROM dividends WHERE year = ? ORDER BY date", (year,))
    rows = c.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = str(year)
    ws.append(["Дата", "WKN", "Акция", "Сумма (€)"])

    colors = ["FFCCCC", "CCFFCC", "CCCCFF", "FFFFCC", "CCFFFF"]
    wkn_colors = {}
    current_row = 2

    for row_data in rows:
        ws.append(row_data)
        wkn = row_data[1]
        if wkn not in wkn_colors:
            wkn_colors[wkn] = colors[len(wkn_colors) % len(colors)]
        fill = PatternFill(start_color=wkn_colors[wkn], end_color=wkn_colors[wkn], fill_type="solid")
        for col in range(1, 5):
            ws.cell(row=current_row, column=col).fill = fill
        current_row += 1

    sum_row = current_row
    ws[f"A{sum_row}"] = "ИТОГО"
    ws[f"D{sum_row}"] = f"=SUM(D2:D{current_row - 1})"
    for col in range(1, 5):
        ws.cell(row=sum_row, column=col).fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

    output_path = Path(f"dividends_{year}.xlsx")
    wb.save(output_path)
    return output_path

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

def add_dividend_to_sheets(date: str, wkn: str, name: str, amount: float):
    try:
        sheet = _get_spreadsheet().sheet1
        col_a = sheet.col_values(1)
        new_row = 3
        while new_row <= len(col_a) and col_a[new_row - 1].strip():
            new_row += 1
        sum_row = new_row + 1
        sheet.update(f"A{new_row}:D{new_row}", [[date, wkn, name, amount]])
        color = get_color_for_wkn(wkn)
        sheet.format(f"A{new_row}:D{new_row}", {"backgroundColor": color})
        sheet.update(f"D{sum_row}", f"=SUM(D3:D{new_row})")
        return True
    except Exception as e:
        logger.error(f"Ошибка Sheets: {e}")
        return False

def delete_from_sheets(date: str):
    try:
        sheet = _get_spreadsheet().sheet1
        col_a = sheet.col_values(1)
        to_del = []
        for i, cell in enumerate(col_a[2:], start=3):
            if cell.strip() == date:
                to_del.append(i)
        for i in sorted(to_del, reverse=True):
            sheet.delete_rows(i)
        col_a_after = sheet.col_values(1)
        last_row = 2
        for i, cell in enumerate(col_a_after[2:], start=3):
            if cell.strip():
                last_row = i
        sum_row = last_row + 1
        sheet.update(f"D{sum_row}", f"=SUM(D3:D{last_row})")
        return len(to_del)
    except Exception as e:
        logger.error(f"Ошибка удаления из Sheets: {e}")
        return 0

# ─────────────── ХЕНДЛЕРЫ ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n"
        "📺 Пришли .m3u/.m3u8/.txt — проверю потоки\n"
        "💰 Скрытые команды: /mysecret"
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
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            input_path = tmp / "input.m3u"
            file = await document.get_file()
            await file.download_to_drive(custom_path=str(input_path))
            await msg.edit_text("🔍 Проверяю потоки... (3–20 мин)")
            try:
                proc = await asyncio.create_subprocess_exec("ffmpeg", "-version", stdout=asyncio.subprocess.DEVNULL)
                await proc.communicate()
                if proc.returncode != 0:
                    raise FileNotFoundError
            except:
                await msg.edit_text("❌ FFmpeg не установлен")
                return
            output_m3u = tmp / "good.m3u"
            cmd = ["python3", COMBINER_SCRIPT, str(tmp), "-w", "4", "-t", "15", "-o", str(output_m3u)]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode != 0 or not output_m3u.is_file() or output_m3u.stat().st_size < 200:
                await msg.edit_text("❌ Не найдено рабочих потоков")
                return
            zip_name = f"m3u_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            zip_path = tmp / zip_name
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.write(output_m3u, "good.m3u")
            if zip_path.stat().st_size > 50 * 1024 * 1024:
                await msg.edit_text("❌ Файл >50 МБ")
                return
            await msg.edit_text("📤 Отправляю...")
            with open(zip_path, "rb") as f:
                await update.message.reply_document(document=f, filename=zip_name)
    except Exception as e:
        logger.exception("Ошибка обработки")
        await update.message.reply_text("💥 Ошибка")

async def handle_hidden_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/mysecret":
        await update.message.reply_text(
            "🔐 Скрытые команды:\n"
            "• <code>wkn123456 45.50euro</code>\n"
            "• <code>isinDE00012345 30euro</code>\n"
            "• <code>del02.06</code>\n"
            "• <code>new27</code>\n"
            "• <code>/divxlsx</code>\n"
            "• <code>/divlog</code>\n"
            "• <code>/divdebug</code>",
            parse_mode="HTML"
        )
        return
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
        except:
            await update.message.reply_text("❌ Ошибка")
        return
    if match := re.fullmatch(r"del(\d{2})\.(\d{2})", text, re.IGNORECASE):
        day, month = match.groups()
        target = f"{day}.{month}.{datetime.now().year}"
        db_del = delete_dividends_by_date(target)
        sheets_del = delete_from_sheets(target)
        await update.message.reply_text(f"🗑️ Удалено: БД={db_del}, Sheets={sheets_del}")
        return
    match = re.fullmatch(r"(?P<prefix>wkn|isin)(?P<code>[a-zA-Z0-9]{6,12})\s+(?P<amount>\d+\.?\d*)\s*euro", text, re.IGNORECASE)
    if match:
        code = match.group("code").upper()
        amount = float(match.group("amount"))
        stock_info = get_wkn_info(code)
        name = stock_info["name"] if stock_info else f"WKN{code}"
        date_str = datetime.now().strftime("%d.%m.%Y")
        add_dividend_to_db(date_str, code, name, amount, stock_info["logo"] if stock_info else "")
        sheets_ok = add_dividend_to_sheets(date_str, code, name, amount)
        await update.message.reply_text(f"✅ {'Sheets + БД' if sheets_ok else 'только БД'}")
        return

async def download_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        xlsx_path = generate_excel()
        with open(xlsx_path, "rb") as f:
            await update.message.reply_document(document=f, filename=xlsx_path.name)
        xlsx_path.unlink()
    except Exception as e:
        logger.error(f"Excel error: {e}")
        await update.message.reply_text("❌ Ошибка Excel")

async def show_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, wkn, name, amount FROM dividends WHERE year = ? ORDER BY created_at DESC LIMIT 10", (datetime.now().year,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("📭 Нет записей")
            return
        text = "📋 Последние 10:\n"
        total = 0
        for date, wkn, name, amount in rows:
            text += f"• {date} | {wkn} | {name} | {amount}€\n"
            total += amount
        text += f"\n💰 Итого: {total:.2f}€"
        await update.message.reply_text(text)
    except:
        await update.message.reply_text("❌ Ошибка лога")

async def divdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        if not b64:
            await update.message.reply_text("❌ GOOGLE_CREDENTIALS_BASE64 не задан")
            return
        creds_dict = json.loads(base64.b64decode(b64).decode('utf-8'))
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8").sheet1
        value = sheet.acell("A1").value or "пусто"
        await update.message.reply_text(f"✅ Подключено!\nA1: {value}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка:\n{str(e)[:300]}")

# ─────────────── FASTAPI ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application
    init_db()
    load_wkn_json()
    application = Application.builder().token(BOT_TOKEN).build()
    await application.initialize()
    await application.start()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mysecret", handle_hidden_commands))
    application.add_handler(CommandHandler("divxlsx", download_excel))
    application.add_handler(CommandHandler("divlog", show_log))
    application.add_handler(CommandHandler("divdebug", divdebug))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hidden_commands))
    yield
    await application.stop()
    await application.shutdown()

app = FastAPI(title="M3U + Dividends Bot", lifespan=lifespan)

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
    except:
        raise HTTPException(500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
