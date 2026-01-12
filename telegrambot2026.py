import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import m3u_handler
import finance_handler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "very-secret")

# ===== COMMAND HANDLERS =====

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🤖 Бот запущен!\n\n"
        "📂 Отправь .m3u/.m3u8 файл для обработки\n"
        "💰 Используй /mysecret для финансовых команд"
    )

async def mysecret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /mysecret - показывает помощь по финансам"""
    help_text = (
        "🔐 <b>Финансовые команды:</b>\n\n"
        "📊 <b>Добавить дивиденды:</b>\n"
        "<code>wkn123456 45.50euro</code>\n"
        "<code>isinDE0000123456 100euro</code>\n\n"
        "🗑 <b>Удалить записи:</b>\n"
        "<code>del02.06</code> - удалить все записи за 02.06.2026\n\n"
        "📈 Данные сохраняются в Google Sheets"
    )
    await update.message.reply_html(help_text)

# ===== MESSAGE HANDLERS =====

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ТОЛЬКО для файлов M3U"""
    doc = update.message.document
    if not doc:
        return
    
    file_name = doc.file_name or "unknown"
    logger.info(f"📂 Получен документ: {file_name}")
    
    # Проверяем расширение файла
    if not any(file_name.lower().endswith(ext) for ext in ['.m3u', '.m3u8', '.txt']):
        await update.message.reply_text(
            "⚠️ Поддерживаются только файлы .m3u, .m3u8 или .txt"
        )
        return
    
    # Передаем обработку в m3u_handler
    await m3u_handler.process_m3u_document(update, context)

async def handle_finance_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ТОЛЬКО для текстовых финансовых команд"""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    logger.info(f"💬 Получен текст: {text[:50]}...")
    
    # Пытаемся обработать как финансовую команду
    response = await finance_handler.handle_finance_command(text)
    
    if response:
        # Команда распознана и обработана
        await update.message.reply_html(response)
    else:
        # Команда не распознана - показываем подсказку
        await update.message.reply_text(
            "❓ Команда не распознана.\n"
            "Используй /mysecret для справки по финансовым командам"
        )

# ===== FASTAPI APPLICATION =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск Telegram бота...")
    
    # Создаем приложение бота
    bot_app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики КОМАНД
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("mysecret", mysecret_command))
    
    # Регистрируем обработчики СООБЩЕНИЙ (порядок важен!)
    # 1. Документы обрабатываются первыми
    bot_app.add_handler(
        MessageHandler(
            filters.Document.ALL & ~filters.COMMAND,
            handle_document
        )
    )
    
    # 2. Текстовые сообщения обрабатываются вторыми
    bot_app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_finance_text
        )
    )
    
    # Инициализируем бота
    await bot_app.initialize()
    await bot_app.start()
    
    # Сохраняем в state приложения
    app.state.tg_app = bot_app
    
    logger.info("✅ Бот успешно запущен")
    logger.info(f"   - Webhook: {WEBHOOK_URL if WEBHOOK_URL else 'Polling mode'}")
    
    yield
    
    # Остановка бота
    logger.info("🛑 Остановка бота...")
    await bot_app.stop()
    await bot_app.shutdown()

# Создаем FastAPI приложение
app = FastAPI(lifespan=lifespan)

# Переменная для webhook URL
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

# ===== ENDPOINTS =====

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    """Обработчик входящих обновлений от Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, app.state.tg_app.bot)
        await app.state.tg_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return Response(status_code=500)

@app.get("/health")
def health():
    """Health check endpoint для Render"""
    return {
        "status": "ok",
        "service": "telegram_bot_2026",
        "webhook_configured": WEBHOOK_URL is not None
    }

@app.get("/")
def root():
    """Корневой endpoint"""
    return {
        "service": "Telegram Bot 2026",
        "status": "running",
        "features": ["M3U processing", "Finance tracking"]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
