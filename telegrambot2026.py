# telegrambot2026.py
import os
import tempfile
import zipfile
import logging
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime
import json
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
from openpyxl import Workbook
from openpyxl.styles import PatternFill
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# ─────────────── КОНФИГ (получаем извне) ───────────────
class Config:
    def __init__(self):
        self.BOT_TOKEN = None
        self.WEBHOOK_SECRET = "change-me-very-secure-secret-2026"
        self.GOOGLE_CREDENTIALS_BASE64 = None
        self.COMBINER_SCRIPT = "m3u_combiner_fixed.py"

config = Config()

# ─────────────── ЛОКАЛЬНАЯ БД ───────────────
DB_PATH = Path("dividends.db")

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
            year INTEGER NOT NULL
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
                c.execute("INSERT OR REPLACE INTO wkn_lookup VALUES (?, ?, ?)", (wkn, name, logo))
            if isin:
                c.execute("INSERT OR REPLACE INTO wkn_lookup VALUES (?, ?, ?)", (isin, name, logo))
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
    return {"name": result[0], "logo": result[1]} if result else None

def add_dividend_to_db(date: str, wkn: str, name: str, amount: float, logo_url: str = ""):
    year = datetime.now().year
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO dividends (date, wkn, name, amount, logo_url, year) VALUES (?, ?, ?, ?, ?, ?)",
              (date, wkn, name, amount, logo_url, year))
    conn.commit()
    conn.close()

def delete_dividends_by_date(date: str):
    year = datetime.now().year
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM dividends WHERE date = ? AND year = ?", (date, year))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

def generate_excel():
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
def _get_spreadsheet():
    b64 = config.GOOGLE_CREDENTIALS_BASE64
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
        color = COLORS[hash(wkn) % len(COLORS)]
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

COLORS = [
    {"red": 1.0, "green": 0.9, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 0.9, "blue": 1.0},
    {"red": 1.0, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 1.0},
]

# ─────────────── ХЕНДЛЕРЫ ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет!\n📺 Пришли .m3u/.m3u8/.txt\n💰 Скрытые команды: /mysecret")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not any((document.file_name or "").lower().endswith(ext) for ext in ('.m3u', '.m3u8', '.txt')):
        return
    msg = await update.message.reply_text("📥 Скачиваю...")
    try:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            input_path = tmp / "input.m3u"
            await document.get_file().download_to_drive(str(input_path))
            await msg.edit_text("🔍 Проверяю потоки...")

            proc = await asyncio.create_subprocess_exec("ffmpeg", "-version", stdout=asyncio.subprocess.DEVNULL)
            await proc.communicate()
            if proc.returncode != 0:
                await msg.edit_text("❌ FFmpeg не установлен")
                return

            output_m3u = tmp / "good.m3u"
            cmd = ["python3", config.COMBINER_SCRIPT, str(tmp), "-w", "4", "-t", "15", "-o", str(output_m3u)]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()

            if not output_m3u.is_file() or output_m3u.stat().st_size < 200:
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
        logger.exception("Ошибка M3U")
        await update.message.reply_text("💥 Ошибка")

async def handle_hidden_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/mysecret":
        await update.message.reply_text(
            "🔐 Команды:\n• <code>wkn123456 45.50euro</code>\n• <code>del02.06</code>",
            parse_mode="HTML"
        )
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

async def download_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        xlsx_path = generate_excel()
        with open(xlsx_path, "rb") as f:
            await update.message.reply_document(document=f, filename=xlsx_path.name)
        xlsx_path.unlink()
    except Exception as e:
        logger.error(f"Excel error: {e}")
        await update.message.reply_text("❌ Ошибка Excel")

# ─────────────── FASTAPI APP ───────────────
def create_app(application: Application) -> FastAPI:
    app = FastAPI(title="M3U + Dividends Bot")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post(f"/webhook/{config.WEBHOOK_SECRET}")
    async def webhook(request: Request):
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.WEBHOOK_SECRET:
            raise HTTPException(403)
        update = Update.de_json(await request.json(), application.bot)
        await application.update_queue.put(update)
        return {"ok": True}

    return app
