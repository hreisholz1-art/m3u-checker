"""
telegrambot2026.py - ТОЛЬКО роутинг и FastAPI
Никакой бизнес-логики! Только маршрутизация.
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

import m3u_handler
import finance_handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "very-secret")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутер для текстовых сообщений → finance_handler"""
    if not update.message or not update.message.text:
        return
    
    response = await finance_handler.handle_finance_command(update.message.text)
    if response:
        await update.message.reply_html(response)

async def route_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутер для документов → m3u_handler"""
    if not update.message or not update.message.document:
        return
    
    await m3u_handler.process_m3u_document(update, context)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл бота"""
    bot_app = Application.builder().token(TOKEN).build()
    
    # ПОРЯДОК ВАЖЕН: сначала TEXT, потом Document
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))
    bot_app.add_handler(MessageHandler(filters.Document.ALL, route_document))
    
    await bot_app.initialize()
    await bot_app.start()
    app.state.tg_app = bot_app
    
    # Установка webhook для Telegram
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=["message"],
            drop_pending_updates=True
        )
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}")
    else:
        logger.info("✅ Bot started in polling mode")
    
    yield
    
    # Удаление webhook при остановке
    if WEBHOOK_URL:
        await bot_app.bot.delete_webhook()
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    data = await request.json()
    await app.state.tg_app.process_update(Update.de_json(data, app.state.tg_app.bot))
    return Response(status_code=200)

@app.get("/")
def root():
    """Root endpoint - zeigt Bot Status"""
    return {
        "status": "running",
        "service": "Telegram Bot 2026",
        "features": ["M3U processing", "Finance tracking"],
        "webhook": WEBHOOK_URL or "polling mode"
    }

@app.get("/health")
def health():
    """Health check für Render"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
