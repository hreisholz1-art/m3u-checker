import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Unsere isolierten Module
import m3u_handler
import finance_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routet Textnachrichten an die Finanz-Logik."""
    if not update.message or not update.message.text:
        return
    
    # Finanz-Check (Pattern Matching passiert intern im Handler)
    response = await finance_handler.handle_finance_command(update.message.text)
    if response:
        await update.message.reply_html(response)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup Application
    bot_app = Application.builder().token(TOKEN).build()
    
    # Handlers registrieren
    bot_app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Bot aktiv.")))
    bot_app.add_handler(MessageHandler(filters.Document.ALL, m3u_handler.process_m3u_document))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    
    await bot_app.initialize()
    await bot_app.start()
    app.state.tg_app = bot_app
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if token != WEBHOOK_SECRET:
        return Response(status_code=403)
    
    data = await request.json()
    await app.state.tg_app.process_update(Update.de_json(data, app.state.tg_app.bot))
    return Response(status_code=200)

@app.get("/health")
def health(): return {"status": "ok"}
