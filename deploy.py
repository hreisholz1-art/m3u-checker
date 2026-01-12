# deploy.py
import os
import logging
from contextlib import asynccontextmanager
from telegram.ext import Application
from telegrambot2026 import config, init_db, load_wkn_json, create_app
from telegrambot2026 import start, handle_document, handle_hidden_commands, download_excel
from telegram.ext import CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────── НАСТРОЙКА ДЛЯ RENDER ───────────────
config.BOT_TOKEN = os.getenv("BOT_TOKEN")
config.WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-very-secure-secret-2026")
config.GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")

if not config.BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")

# ─────────────── LIFESPAN ───────────────
@asynccontextmanager
async def lifespan(app):
    init_db()
    load_wkn_json()
    bot_app = Application.builder().token(config.BOT_TOKEN).build()
    await bot_app.initialize()
    await bot_app.start()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("divxlsx", download_excel))
    bot_app.add_handler(CommandHandler("mysecret", handle_hidden_commands))
    bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hidden_commands))
    
    app.state.tg_app = bot_app
    yield
    await bot_app.stop()
    await bot_app.shutdown()

# ─────────────── ЗАПУСК ───────────────
app = create_app(Application.builder().token(config.BOT_TOKEN).build())
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
