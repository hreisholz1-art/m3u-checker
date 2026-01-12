import re
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os
import base64

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Секретные команды
SECRET_COMMANDS = {
    "wkn": r'^wkn(\d{5,6})\s+(\d+\.?\d*)euro$',
    "del": r'^del(\d{2}\.\d{2})$',
}

def get_google_sheets_client():
    try:
        credentials_base64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
        if not credentials_base64:
            logger.error("GOOGLE_CREDENTIALS_BASE64 не установлен")
            return None

        credentials_json = base64.b64decode(credentials_base64).decode("utf-8")
        credentials = Credentials.from_service_account_info(
            eval(credentials_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка авторизации в Google Sheets: {e}")
        return None

def handle_finance_command(text: str) -> str | None:
    for cmd, pattern in SECRET_COMMANDS.items():
        match = re.compile(pattern, re.IGNORECASE).match(text)
        if match:
            logger.info(f"Распознана команда: {cmd} {match.groups()}")
            if cmd == "wkn":
                wkn, amount = match.groups()
                return f"Обработка WKN {wkn}: сумма {amount} EUR"
            elif cmd == "del":
                date = match.groups()[0]
                return f"Удаление записи от {date}"
    logger.info(f"Нераспознанная команда: {text}")
    return None
