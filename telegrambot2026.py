import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import m3u_handler
import finance_handler

# ===== КОНФИГУРАЦИЯ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "very-secret")

# ===== ТЕЛЕГРАМ ХЕНДЛЕРЫ =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "📁 **M3U Обработчик**\n"
        "   → Отправь файл .m3u/.m3u8/.txt\n"
        "   → Я проверю все потоки и верну рабочие\n\n"
        "📈 **Финансовый трекер**\n"
        "   → `wkn123456 45.50euro` - добавить дивиденд\n"
        "   → `del02.06` - удалить записи за дату\n"
        "   → `/mysecret` - показать все команды"
    )

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Маршрутизатор текстовых сообщений"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    
    # Финансовые команды имеют приоритет
    response = await finance_handler.handle_finance_command(text)
    
    if response:
        # Финансовая команда обработана
        await update.message.reply_html(response)
    elif text == "/mysecret":
        # Явный вызов команды /mysecret
        await update.message.reply_text(
            "🔐 **Скрытые команды:**\n\n"
            "• <code>wkn123456 45.50euro</code> - добавить дивиденд\n"
            "• <code>isinDE00012345 30euro</code> - добавить по ISIN\n"
            "• <code>del02.06</code> - удалить записи за 2 июня\n"
            "• <code>/mysecret</code> - показать эту справку\n\n"
            "📁 **M3U обработка:**\n"
            "• Просто отправь файл .m3u/.m3u8/.txt",
            parse_mode="HTML"
        )
    else:
        # Неизвестная текстовая команда
        await update.message.reply_text(
            "ℹ️ Я могу:\n"
            "• Обрабатывать M3U файлы (отправь файл)\n"
            "• Вести учёт дивидендов (например: wkn123456 100euro)\n"
            "• Показать все команды: /mysecret"
        )

# ===== FASTAPI LIFESPAN =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Инициализация бота
    bot_app = Application.builder().token(TOKEN).build()
    
    # ВАЖНО: Порядок имеет значение!
    # 1. Сначала команды
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("mysecret", text_router))  # Обрабатывается в text_router
    
    # 2. Затем текстовые сообщения (финансовые команды)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    
    # 3. В конце документы (M3U файлы)
    bot_app.add_handler(MessageHandler(filters.Document.ALL, m3u_handler.process_m3u_document))
    
    # Инициализация
    await bot_app.initialize()
    await bot_app.start()
    
    # Сохраняем в состоянии приложения
    app.state.tg_app = bot_app
    
    logger.info("✅ Бот запущен успешно")
    yield
    
    # Завершение работы
    logger.info("🛑 Завершение работы бота...")
    await bot_app.stop()
    await bot_app.shutdown()

# ===== FASTAPI APP =====
app = FastAPI(
    title="Telegram Bot 2026",
    description="M3U Processor & Finance Tracker",
    version="1.0.0",
    lifespan=lifespan
)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    """Webhook endpoint для Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, app.state.tg_app.bot)
        await app.state.tg_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=500)

@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    return {
        "status": "healthy",
        "service": "telegram-bot-2026",
        "components": {
            "bot": "initialized",
            "m3u_handler": "ready",
            "finance_handler": "ready"
        }
    }

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": "Telegram Bot 2026",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "webhook": f"/webhook/{WEBHOOK_SECRET}",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
