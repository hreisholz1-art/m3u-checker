"""
finance_handler.py - ТОЛЬКО финансовая логика
Google Sheets + WKN команды
"""
import os
import re
import json
import base64
import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

SHEET_ID = "1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8"
WKN_JSON_PATH = "wkn.json.txt"

# Regex patterns
PATTERN_HELP = re.compile(r"^/mysecret$")
PATTERN_WKN = re.compile(r"^(?P<prefix>wkn|isin)(?P<code>[a-zA-Z0-9]{6,12})\s+(?P<amount>\d+\.?\d*)\s*euro", re.IGNORECASE)
PATTERN_DEL = re.compile(r"^del(\d{2})\.(\d{2})$", re.IGNORECASE)

COLORS = [
    {"red": 1.0, "green": 0.9, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 0.9, "blue": 1.0},
    {"red": 1.0, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 1.0},
]

def load_stock_info(code: str) -> str | None:
    """Загружает название акции из wkn.json"""
    try:
        if os.path.exists(WKN_JSON_PATH):
            with open(WKN_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if item.get("wkn", "").upper() == code or item.get("isin", "").upper() == code:
                        return item.get("name")
    except Exception as e:
        logger.error(f"WKN JSON error: {e}")
    return None

def get_client():
    """Авторизация в Google Sheets"""
    try:
        b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        if not b64:
            logger.warning("GOOGLE_CREDENTIALS_BASE64 not set")
            return None
        
        creds_dict = json.loads(base64.b64decode(b64).decode('utf-8'))
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None

async def handle_finance_command(text: str) -> str | None:
    """
    Обрабатывает финансовые команды.
    Возвращает ответ для пользователя или None если команда не распознана.
    """
    text_clean = text.strip()
    
    # Команда /mysecret
    if PATTERN_HELP.fullmatch(text_clean):
        return (
            "🔐 <b>Финансовые команды:</b>\n\n"
            "📊 <code>wkn123456 45.50euro</code>\n"
            "📊 <code>isinDE0000123456 100euro</code>\n\n"
            "🗑 <code>del02.06</code> - удалить записи за дату\n\n"
            "💡 Все данные сохраняются в Google Sheets"
        )
    
    client = get_client()
    if not client:
        return None
    
    try:
        sh = client.open_by_key(SHEET_ID)
        ws = sh.sheet1
        
        # Команда добавления дивидендов: wknXXXXXX amount euro
        if match := PATTERN_WKN.fullmatch(text_clean):
            code = match.group("code").upper()
            amount = float(match.group("amount"))
            stock_name = load_stock_info(code) or f"WKN {code}"
            
            date_str = datetime.now().strftime("%d.%m.%Y")
            row = [date_str, code, stock_name, amount]
            
            ws.append_row(row, value_input_option="USER_ENTERED")
            last_row = len(ws.get_all_values())
            
            # Цветовая раскраска строки
            color = COLORS[hash(code) % len(COLORS)]
            ws.format(f"A{last_row}:D{last_row}", {"backgroundColor": color})
            
            # Обновление суммы
            ws.update_acell("C1", "=SUM(D2:D1000)")
            
            return f"✅ Записано: <b>{stock_name}</b> ({amount} €)"
        
        # Команда удаления: delDD.MM
        if match := PATTERN_DEL.fullmatch(text_clean):
            day, month = match.groups()
            target_date = f"{day}.{month}.2026"
            rows = ws.get_all_values()
            
            to_del = [i+1 for i, r in enumerate(rows) if r and r[0] == target_date]
            
            for i in sorted(to_del, reverse=True):
                ws.delete_rows(i)
            
            ws.update_acell("C1", "=SUM(D2:D1000)")
            
            return f"🗑 Удалено {len(to_del)} строк за {target_date}"
    
    except Exception as e:
        logger.error(f"Finance handler error: {e}")
        return "❌ Ошибка при обработке команды"
    
    return None
