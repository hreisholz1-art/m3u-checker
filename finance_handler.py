import os
import re
import json
import base64
import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# [cite_start]Konfiguration [cite: 5, 20, 24]
[cite_start]SHEET_ID = "1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8" [cite: 24]
[cite_start]WKN_JSON_PATH = "wkn.json.txt" [cite: 2, 4]

# [cite_start]Regex Patterns [cite: 18]
[cite_start]PATTERN_HELP = re.compile(r"^/mysecret$") [cite: 13]
[cite_start]PATTERN_WKN = re.compile(r"^(?P<prefix>wkn|isin)(?P<code>[a-zA-Z0-9]{6,12})\s+(?P<amount>\d+\.?\d*)\s*euro", re.IGNORECASE) [cite: 18, 19]
[cite_start]PATTERN_DEL = re.compile(r"^del(\d{2})\.(\d{2})$", re.IGNORECASE) [cite: 16]
[cite_start]PATTERN_NEW = re.compile(r"^new(\d{2})$", re.IGNORECASE) [cite: 14]

COLORS = [
    {"red": 1.0, "green": 0.9, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 0.9, "blue": 1.0},
    {"red": 1.0, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 1.0},
[cite_start]] [cite: 4]

def load_stock_info(code):
    try:
        if os.path.exists(WKN_JSON_PATH):
            with open(WKN_JSON_PATH, "r", encoding="utf-8") as f:
                [cite_start]data = json.load(f) [cite: 2]
                for item in data:
                    [cite_start]if item.get("wkn", "").upper() == code or item.get("isin", "").upper() == code: [cite: 3]
                        [cite_start]return item.get("name") [cite: 2]
    except Exception as e:
        logger.error(f"Error loading WKN: {e}")
    return None

def get_client():
    try:
        [cite_start]b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64") [cite: 5, 23]
        if not b64: return None
        [cite_start]creds_dict = json.loads(base64.b64decode(b64).decode('utf-8')) [cite: 23]
        [cite_start]scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] [cite: 24]
        [cite_start]creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope) [cite: 24]
        [cite_start]return gspread.authorize(creds) [cite: 24]
    except Exception as e:
        logger.error(f"Auth Error: {e}")
        return None

async def handle_finance_command(text: str) -> str | None:
    text_clean = text.strip()

    if PATTERN_HELP.fullmatch(text_clean):
        # Hier lag vermutlich der Syntax-Fehler durch falsche Verkettung oder Einrückung
        msg = "🔐 <b>Команды:</b>\n"
        msg += "<code>wkn123456 45.50euro</code>\n"
        msg += "<code>del02.06</code>\n"
        [cite_start]msg += "<code>new27</code>" [cite: 13, 14]
        return msg

    client = get_client()
    if not client: return None
    
    try:
        [cite_start]sh = client.open_by_key(SHEET_ID) [cite: 24]
        ws = sh.sheet1

        # WKN/ISIN Logik
        if match := PATTERN_WKN.fullmatch(text_clean):
            [cite_start]code = match.group("code").upper() [cite: 19]
            [cite_start]amount = float(match.group("amount")) [cite: 19]
            [cite_start]stock_name = load_stock_info(code) or f"WKN {code}" [cite: 19, 20]
            
            [cite_start]date_str = datetime.now().strftime("%d.%m.%Y") [cite: 21]
            [cite_start]row = [date_str, code, stock_name, amount] [cite: 22]
            
            [cite_start]ws.append_row(row, value_input_option="USER_ENTERED") [cite: 22]
            [cite_start]last_row = len(ws.get_all_values()) [cite: 21]
            
            # Farbe setzen
            [cite_start]color = COLORS[hash(code) % len(COLORS)] [cite: 4, 22]
            [cite_start]ws.format(f"A{last_row}:D{last_row}", {"backgroundColor": color}) [cite: 22]
            
            # Summe in C1 aktualisieren (für Spalte D)
            [cite_start]ws.update_acell("C1", "=SUM(D2:D1000)") [cite: 17, 22]
            return f"✅ Записано: <b>{stock_name}</b> ({amount} €)"

        # Delete Logik
        if match := PATTERN_DEL.fullmatch(text_clean):
            [cite_start]day, month = match.groups() [cite: 16]
            [cite_start]target_date = f"{day}.{month}.2026" [cite: 16]
            [cite_start]rows = ws.get_all_values() [cite: 17]
            [cite_start]to_del = [i+1 for i, r in enumerate(rows) if r and r[0] == target_date] [cite: 17]
            
            for i in sorted(to_del, reverse=True):
                [cite_start]ws.delete_rows(i) [cite: 17]
            
            [cite_start]ws.update_acell("C1", "=SUM(D2:D1000)") [cite: 17]
            [cite_start]return f"🗑 Удалено {len(to_del)} строк за {target_date}" [cite: 18]

    except Exception as e:
        logger.error(f"Finance Handler Error: {e}")
    
    return None
