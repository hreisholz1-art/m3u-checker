import os
import re
import json
import base64
import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# Konfiguration
SHEET_ID = "1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8"
WKN_JSON_PATH = "wkn.json.txt"

# Regex Patterns [cite: 14, 16, 18]
PATTERN_HELP = re.compile(r"^/mysecret$")
PATTERN_WKN = re.compile(r"^(?P<prefix>wkn|isin)(?P<code>[a-zA-Z0-9]{6,12})\s+(?P<amount>\d+\.?\d*)\s*euro", re.IGNORECASE)
PATTERN_DEL = re.compile(r"^del(\d{2})\.(\d{2})$", re.IGNORECASE)
PATTERN_NEW = re.compile(r"^new(\d{2})$", re.IGNORECASE)

# Palette aus deinem Originalcode [cite: 4]
COLORS = [
    {"red": 1.0, "green": 0.9, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 0.9, "blue": 1.0},
    {"red": 1.0, "green": 1.0, "blue": 0.9},
    {"red": 0.9, "green": 1.0, "blue": 1.0},
]

def load_stock_info(code):
    """Lädt Namen aus der wkn.json.txt[cite: 2, 3]."""
    try:
        if os.path.exists(WKN_JSON_PATH):
            with open(WKN_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if item.get("wkn", "").upper() == code or item.get("isin", "").upper() == code:
                        return item.get("name")
    except Exception as e:
        logger.error(f"Fehler beim Laden der WKN-Daten: {e}")
    return None

def get_gspread_client():
    try:
        b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64") # [cite: 5]
        if not b64: return None
        creds_dict = json.loads(base64.b64decode(b64).decode('utf-8'))
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Auth Fehler: {e}")
        return None

async def handle_finance_command(text: str) -> str | None:
    text = text.strip()

    # 1. Hilfe [cite: 14]
    if PATTERN_HELP.fullmatch(text):
        return (
            "🔐 <b>Versteckte Befehle:</b>\n\n"
            "• <code>wkn123456 45.50euro</code> - Eintrag hinzufügen\n"
            "• <code>del02.06</code> - Löscht Einträge vom 2. Juni\n"
            "• <code>new27</code> - Neues Blatt für 2027"
        )

    client = get_gspread_client()
    if not client: return None
    sh = client.open_by_key(SHEET_ID)

    # 2. WKN/ISIN Eintrag (OHNE LOGO) [cite: 19, 22]
    if match := PATTERN_WKN.fullmatch(text):
        try:
            code = match.group("code").upper()
            amount = float(match.group("amount"))
            stock_name = load_stock_info(code) or f"Aktie {code}"
            
            ws = sh.sheet1
            date_str = datetime.now().strftime("%d.%m.%Y")
            
            # Neue Zeile: [Datum, WKN, Name, Betrag]
            row_data = [date_str, code, stock_name, amount]
            ws.append_row(row_data, value_input_option="USER_ENTERED")
            
            # Formatierung 
            last_row = len(ws.get_all_values())
            color = COLORS[hash(code) % len(COLORS)]
            ws.format(f"A{last_row}:D{last_row}", {"backgroundColor": color})
            
            # Summe in D2 aktualisieren 
            ws.update_acell("D2", f"=SUM(D3:D{max(100, last_row)})")
            return f"✅ Gebucht: {stock_name} ({amount}€)"
        except Exception as e:
            logger.error(f"WKN Error: {e}")
            return None

    # 3. Löschen [cite: 17, 18]
    if match := PATTERN_DEL.fullmatch(text):
        try:
            day, month = match.groups()
            target = f"{day}.{month}.{datetime.now().year}"
            ws = sh.sheet1
            rows = ws.get_all_values()
            
            to_del = [i+1 for i, r in enumerate(rows) if len(r) > 0 and r[0] == target]
            for i in sorted(to_del, reverse=True):
                ws.delete_rows(i)
            
            ws.update_acell("D2", "=SUM(D3:D1000)")
            return f"🗑️ {len(to_del)} Einträge für {target} gelöscht."
        except Exception as e:
            logger.error(f"Del Error: {e}")
            return None

    # 4. Neues Blatt [cite: 15]
    if match := PATTERN_NEW.fullmatch(text):
        year = f"20{match.group(1)}"
        try:
            sh.duplicate_sheet(sh.sheet1.id, new_sheet_name=year)
            ws = sh.worksheet(year)
            ws.clear()
            ws.update("A1:D2", [
                ["Datum", "WKN", "Aktie", "Summe (€)"],
                ["", "", "", "=SUM(D3:D1000)"]
            ])
            return f"📅 Blatt {year} wurde erstellt."
        except Exception as e:
            logger.error(f"New Error: {e}")
            return None

    return None
