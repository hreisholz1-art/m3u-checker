import os
import re
import json
import base64
import logging
import hashlib
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# Google Sheet ID (Hardcoded wie gewünscht)
SHEET_ID = "1r2P4pF1TcICCuUAZNZm5lEpykVVZe94QZQ6-z6CrNg8"

# Regex Pattern
PATTERN_HELP = re.compile(r"^/mysecret$")
PATTERN_WKN = re.compile(r"^wkn(\w+)\s+([\d.,]+)euro$", re.IGNORECASE)
PATTERN_DEL = re.compile(r"^del(\d{2}\.\d{2})$", re.IGNORECASE)
PATTERN_NEW = re.compile(r"^new(\d{2})$", re.IGNORECASE)

COLORS = [
    {"red": 0.8, "green": 0.9, "blue": 1.0},  # Hellblau
    {"red": 0.9, "green": 1.0, "blue": 0.8},  # Hellgrün
    {"red": 1.0, "green": 0.9, "blue": 0.9},  # Hellrot
    {"red": 1.0, "green": 1.0, "blue": 0.8},  # Gelb
    {"red": 0.9, "green": 0.8, "blue": 1.0},  # Lila
]

def get_gspread_client():
    """Authentifiziert sich bei Google mit Env-Var."""
    try:
        creds_b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        if not creds_b64:
            logger.error("GOOGLE_CREDENTIALS_BASE64 fehlt.")
            return None
        
        creds_json = json.loads(base64.b64decode(creds_b64).decode('utf-8'))
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Google Auth Fehler: {e}")
        return None

def _get_spreadsheet(client):
    try:
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        logger.error(f"Spreadsheet Error: {e}")
        return None

def handle_finance_command(text: str) -> str | None:
    """
    Analysiert den Text. Wenn ein Finanz-Muster passt, führe Aktion aus.
    Gibt Antwort-String zurück oder None, wenn kein Match.
    """
    text = text.strip()

    # 1. Hilfe
    if PATTERN_HELP.fullmatch(text):
        return (
            "<b>Versteckte Befehle:</b>\n"
            "<code>wkn123456 45.50euro</code> - Zeile hinzufügen\n"
            "<code>del02.06</code> - Löscht Zeilen (Tag.Monat)\n"
            "<code>new27</code> - Neues Blatt '2027' erstellen"
        )

    client = get_gspread_client()
    if not client:
        return None  # Silent fail

    # 2. WKN Eintrag: wkn123456 45.50euro
    match_wkn = PATTERN_WKN.fullmatch(text)
    if match_wkn:
        try:
            wkn = match_wkn.group(1).upper()
            amount_str = match_wkn.group(2).replace(',', '.')
            amount = float(amount_str)
            
            sh = _get_spreadsheet(client)
            ws = sh.sheet1  # Standardmäßig das erste Blatt oder nach Jahr wählen
            
            # Farbe berechnen
            color_idx = hash(wkn) % len(COLORS)
            bg_color = COLORS[color_idx]
            
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # Zeile vorbereiten: [Datum, WKN_RAW, "WKN...", Betrag]
            row_data = [today_str, wkn, f"WKN{wkn}", amount]
            
            # Einfügen (Append)
            ws.append_row(row_data)
            
            # Formatierung der letzten Zeile holen
            last_row = len(ws.get_all_values())
            
            # Farbe setzen (gspread format)
            fmt = {"backgroundColor": bg_color}
            ws.format(f"A{last_row}:D{last_row}", fmt)
            
            # Formel aktualisieren in D2
            ws.update_acell("D2", f"=SUM(D3:D{max(1000, last_row)})")
            
            return f"✅ Gespeichert: {wkn} - {amount:.2f}€"
        except Exception as e:
            logger.error(f"WKN Error: {e}")
            return None

    # 3. Löschen: del02.06
    match_del = PATTERN_DEL.fullmatch(text)
    if match_del:
        try:
            date_part = match_del.group(1)
            current_year = datetime.now().year
            target_date = f"{current_year}-{date_part.split('.')[1]}-{date_part.split('.')[0]}" # YYYY-MM-DD
            
            sh = _get_spreadsheet(client)
            ws = sh.sheet1
            
            rows = ws.get_all_values()
            # Finde Indizes (von unten nach oben löschen, um Index-Verschiebung zu vermeiden)
            to_delete = []
            for i, row in enumerate(rows):
                if i < 2: continue # Header skip
                if row[0] == target_date:
                    to_delete.append(i + 1) # gspread ist 1-basiert
            
            for idx in reversed(to_delete):
                ws.delete_rows(idx)
                
            if to_delete:
                # Formel update
                ws.update_acell("D2", f"=SUM(D3:D1000)")
                return f"🗑️ {len(to_delete)} Zeilen vom {target_date} gelöscht."
            return "Keine Einträge für dieses Datum gefunden."
        except Exception as e:
            logger.error(f"Delete Error: {e}")
            return None

    # 4. Neues Jahr: new27
    match_new = PATTERN_NEW.fullmatch(text)
    if match_new:
        try:
            year_short = match_new.group(1)
            new_sheet_name = f"20{year_short}"
            
            sh = _get_spreadsheet(client)
            
            try:
                # Versuche existierendes zu holen oder Fehler werfen
                sh.worksheet(new_sheet_name)
                return f"Blatt {new_sheet_name} existiert bereits."
            except:
                pass # Existiert nicht, gut.

            # Duplizieren des ersten Blattes als Template
            sh.sheet1.duplicate(new_sheet_name=new_sheet_name)
            new_ws = sh.worksheet(new_sheet_name)
            
            # Inhalt leeren (ab Zeile 3), Header behalten
            all_rows = len(new_ws.get_all_values())
            if all_rows > 2:
                new_ws.batch_clear([f"A3:D{all_rows}"])
            
            new_ws.update_acell("D2", "=SUM(D3:D1000)")
            
            return f"📅 Blatt '{new_sheet_name}' erfolgreich erstellt."
        except Exception as e:
            logger.error(f"New Sheet Error: {e}")
            return None

    return None