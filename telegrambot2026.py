import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import m3u_handler
import finance_handler

# Import deployment configuration
try:
    from deploy import (
        BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL,
        GOOGLE_CREDENTIALS_BASE64, LOG_LEVEL,
        M3U_MAX_WORKERS, M3U_TIMEOUT_SECONDS
    )
    IS_PRODUCTION = True
    CONFIG_SOURCE = "deploy.py (PRODUCTION)"
except ImportError:
    # Fallback to environment variables (compatibility mode)
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "fallback-secret")
    WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
    GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    M3U_MAX_WORKERS = int(os.getenv("M3U_MAX_WORKERS", "4"))
    M3U_TIMEOUT_SECONDS = int(os.getenv("M3U_TIMEOUT_SECONDS", "10"))
    IS_PRODUCTION = False
    CONFIG_SOURCE = "environment variables"

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set Google credentials if available
if GOOGLE_CREDENTIALS_BASE64:
    os.environ["GOOGLE_CREDENTIALS_BASE64"] = GOOGLE_CREDENTIALS_BASE64

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_text = (
        "🤖 **Telegram Bot 2026**\n\n"
        "**Available Functions:**\n"
        "📁 **M3U Playlist Processing**\n"
        "   → Send any .m3u, .m3u8, or .txt file\n"
        "   → Bot will test streams and return working ones\n\n"
        "📈 **Finance Tracker (Hidden)**\n"
        "   → `wknCODE 123.45euro` - Add stock transaction\n"
        "   → `delDD.MM` - Delete entries for a date\n"
        "   → `/mysecret` - Show finance commands\n\n"
        "🔧 *Running in {} mode*"
    ).format("PRODUCTION" if IS_PRODUCTION else "DEVELOPMENT")
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def mysecret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mysecret command - shows finance help"""
    help_text = (
        "🔐 **Finance Tracker Commands**\n\n"
        "**Add transaction:**\n"
        "`wkn123456 45.50euro`\n"
        "`isinDE0001234567 100euro`\n\n"
        "**Delete transactions:**\n"
        "`del02.06` - Delete all entries for 02.06.2026\n\n"
        "**Examples:**\n"
        "• `wknBASF11 150.75euro`\n"
        "• `isinDE0007037129 85euro`\n"
        "• `del15.01`\n\n"
        "📍 *Data is saved to Google Sheets*"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route text messages to appropriate handlers"""
    if not update.message or not update.message.text:
        return
    
    # Try to process as finance command first
    response = await finance_handler.handle_finance_command(update.message.text)
    if response:
        await update.message.reply_html(response)
        return
    
    # If not a finance command and not a command, show help
    if not update.message.text.startswith('/'):
        await update.message.reply_text(
            "ℹ️ Send me an M3U file to process, "
            "or use finance commands like `wkn123456 100euro`",
            parse_mode="Markdown"
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(f"🚀 Starting bot with config from: {CONFIG_SOURCE}")
    logger.info(f"Mode: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is not set!")
        raise ValueError("BOT_TOKEN environment variable is required")
    
    # Initialize bot application
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("mysecret", mysecret_command))
    bot_app.add_handler(MessageHandler(filters.Document.ALL, m3u_handler.process_m3u_document))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    
    # Configure webhook or polling
    if WEBHOOK_URL and IS_PRODUCTION:
        # PRODUCTION: Use webhooks
        await bot_app.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET
        )
        logger.info(f"✅ Webhook set: {WEBHOOK_URL[:50]}...")
        logger.info("📡 Running in WEBHOOK mode")
    else:
        # DEVELOPMENT: Use polling (will be started manually)
        logger.info("🔄 Running in POLLING mode (use for local testing)")
    
    await bot_app.initialize()
    await bot_app.start()
    app.state.tg_app = bot_app
    
    logger.info("✅ Bot started successfully")
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down bot...")
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("✅ Bot shut down")

# Create FastAPI app
app = FastAPI(
    title="Telegram Bot 2026",
    description="M3U Processor & Finance Tracker",
    version="2.0.0",
    lifespan=lifespan
)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    """Webhook endpoint for Telegram (Production only)"""
    if not IS_PRODUCTION:
        return {"error": "Webhook only available in production"}
    
    data = await request.json()
    update = Update.de_json(data, app.state.tg_app.bot)
    await app.state.tg_app.process_update(update)
    return Response(status_code=200)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mode": "production" if IS_PRODUCTION else "development",
        "config_source": CONFIG_SOURCE,
        "features": {
            "m3u_processing": True,
            "finance_tracker": bool(GOOGLE_CREDENTIALS_BASE64)
        }
    }

@app.get("/")
async def root():
    """Root endpoint with information"""
    return {
        "service": "Telegram Bot 2026",
        "endpoints": {
            "health": "/health",
            "webhook": f"/webhook/{WEBHOOK_SECRET}",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    # This block only runs in local development
    import uvicorn
    
    logger.info("🏃 Starting in local development mode...")
    logger.info("⚠️  Note: For production, use Render/Gunicorn")
    
    uvicorn.run(
        "telegrambot2026:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
