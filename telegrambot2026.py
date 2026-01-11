import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import m3u_handler  # Твоя стабильная часть
import finance_handler # Наша финансовая логика

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "very-secret")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Маршрутизатор текстовых сообщений [cite: 26]"""
    if not update.message or not update.message.text:
        return
    
    # Пытаемся обработать как финансовую команду [cite: 13, 26]
    response = await finance_handler.handle_finance_command(update.message.text)
    if response:
        await update.message.reply_html(response)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация бота 
    bot_app = Application.builder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Бот запущен."))) [cite: 5]
    bot_app.add_handler(MessageHandler(filters.Document.ALL, m3u_handler.process_m3u_document)) [cite: 6, 26]
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router)) [cite: 26]
    
    await bot_app.initialize()
    await bot_app.start()
    app.state.tg_app = bot_app
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    data = await request.json()
    await app.state.tg_app.process_update(Update.de_json(data, app.state.tg_app.bot)) [cite: 27]
    return Response(status_code=200)

@app.get("/health")
def health(): return {"status": "ok"}
