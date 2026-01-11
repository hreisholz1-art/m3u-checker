import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

import m3u_handler
import finance_handler

# ===================================================================
# KONFIGURATION - Import aus deploy.py (für Production)
# ===================================================================
try:
    from deploy import (
        BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL,
        GOOGLE_CREDENTIALS_BASE64, LOG_LEVEL,
        M3U_MAX_WORKERS, M3U_TIMEOUT_SECONDS,
        ALLOWED_USER_IDS
    )
    IS_PRODUCTION = True
    CONFIG_SOURCE = "deploy.py"
    print(f"✅ Konfiguration geladen von: {CONFIG_SOURCE}")
except ImportError as e:
    print(f"⚠️  deploy.py nicht gefunden, verwende Umgebungsvariablen: {e}")
    # Fallback zu Umgebungsvariablen
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-change-me")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    M3U_MAX_WORKERS = int(os.getenv("M3U_MAX_WORKERS", "4"))
    M3U_TIMEOUT_SECONDS = int(os.getenv("M3U_TIMEOUT_SECONDS", "10"))
    
    # Webhook URL für Production
    WEBHOOK_URL = None
    if RENDER_EXTERNAL_URL:
        WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    
    # Erlaubte User IDs
    allowed_ids = os.getenv("ALLOWED_USER_IDS", "")
    ALLOWED_USER_IDS = [int(i.strip()) for i in allowed_ids.split(",") if i.strip()] if allowed_ids else []
    
    IS_PRODUCTION = RENDER_EXTERNAL_URL is not None
    CONFIG_SOURCE = "environment variables"

# ===================================================================
# LOGGING KONFIGURATION
# ===================================================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Google Credentials setzen (falls vorhanden)
if GOOGLE_CREDENTIALS_BASE64:
    os.environ["GOOGLE_CREDENTIALS_BASE64"] = GOOGLE_CREDENTIALS_BASE64
    logger.info("✅ Google Sheets Credentials gesetzt")
else:
    logger.warning("⚠️  GOOGLE_CREDENTIALS_BASE64 nicht gesetzt - Finance-Funktionen deaktiviert")

# ===================================================================
# BOT HANDLER FUNKTIONEN
# ===================================================================
def is_user_allowed(user_id: int) -> bool:
    """Prüft, ob der User Zugriff hat"""
    if not ALLOWED_USER_IDS:  # Liste leer = alle erlaubt
        return True
    return user_id in ALLOWED_USER_IDS

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ Zugriff verweigert.")
        return
    
    welcome_text = (
        f"👋 Hallo {user.first_name}!\n\n"
        "🤖 **Telegram Bot 2026**\n\n"
        "📁 **M3U Playlist Verarbeitung**\n"
        "   → Sende eine .m3u, .m3u8 oder .txt Datei\n"
        "   → Ich teste alle Streams und gebe funktionierende zurück\n\n"
    )
    
    # Finance Feature nur anzeigen, wenn konfiguriert
    if GOOGLE_CREDENTIALS_BASE64:
        welcome_text += (
            "📈 **Finanz Tracker**\n"
            "   → `wknCODE 123.45euro` - Aktie hinzufügen\n"
            "   → `delDD.MM` - Einträge für ein Datum löschen\n"
            "   → `/mysecret` - Alle Befehle anzeigen\n\n"
        )
    
    welcome_text += (
        f"🔧 *Modus: {'PRODUCTION' if IS_PRODUCTION else 'ENTWICKLUNG'}*\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def mysecret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mysecret command - Finance Hilfe"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Zugriff verweigert.")
        return
    
    if not GOOGLE_CREDENTIALS_BASE64:
        await update.message.reply_text(
            "⚠️ Finance-Funktionen sind nicht konfiguriert.\n"
            "Bitte GOOGLE_CREDENTIALS_BASE64 Umgebungsvariable setzen."
        )
        return
    
    help_text = (
        "🔐 **Finanz Tracker Befehle**\n\n"
        "**Transaktion hinzufügen:**\n"
        "`wkn123456 45.50euro`\n"
        "`isinDE0001234567 100euro`\n\n"
        "**Transaktionen löschen:**\n"
        "`del02.06` - Alle Einträge für 02.06.2026 löschen\n\n"
        "**Beispiele:**\n"
        "• `wknBASF11 150.75euro`\n"
        "• `isinDE0007037129 85euro`\n"
        "• `del15.01`\n\n"
        "📍 *Daten werden in Google Sheets gespeichert*\n"
        f"📊 *Modus: {'PRODUCTION' if IS_PRODUCTION else 'ENTWICKLUNG'}*"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - Systemstatus"""
    if not is_user_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Zugriff verweigert.")
        return
    
    status_text = (
        "📊 **System Status**\n\n"
        f"• **Bot:** {'✅ Online' if BOT_TOKEN else '❌ Fehlt Token'}\n"
        f"• **Google Sheets:** {'✅ Konfiguriert' if GOOGLE_CREDENTIALS_BASE64 else '❌ Nicht konfiguriert'}\n"
        f"• **Modus:** {'🚀 PRODUCTION' if IS_PRODUCTION else '💻 ENTWICKLUNG'}\n"
        f"• **Konfiguration:** {CONFIG_SOURCE}\n"
        f"• **M3U Worker:** {M3U_MAX_WORKERS}\n"
        f"• **User ID:** {update.effective_user.id}\n"
        f"• **Zugriff:** {'✅ Erlaubt' if is_user_allowed(update.effective_user.id) else '❌ Verweigert'}\n\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route Text-Nachrichten zu passenden Handlern"""
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ Zugriff verweigert.")
        return
    
    text = update.message.text.strip()
    
    # Prüfe ob es eine Finance-Kommando ist
    response = await finance_handler.handle_fance_command(text)
    if response:
        await update.message.reply_html(response)
        return
    
    # Wenn kein Kommando erkannt wurde
    if not text.startswith('/'):
        help_msg = (
            "ℹ️ **Verfügbare Aktionen:**\n\n"
            "1. 📁 **M3U Datei senden**\n"
            "   → .m3u, .m3u8 oder .txt\n\n"
        )
        
        if GOOGLE_CREDENTIALS_BASE64:
            help_msg += (
                "2. 📈 **Finance Befehle**\n"
                "   → `wknCODE betrageuro`\n"
                "   → `delDD.MM`\n"
                "   → `/mysecret` für Hilfe\n\n"
            )
        
        help_msg += (
            "3. 🔧 **System Befehle**\n"
            "   → `/start` - Willkommensnachricht\n"
            "   → `/status` - Systemstatus\n"
            "   → `/mysecret` - Finance Hilfe"
        )
        
        await update.message.reply_text(help_msg, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot"""
    logger.error(f"Update {update} caused error: {context.error}")
    
    if update and update.effective_user:
        try:
            await update.effective_user.send_message(
                "❌ Es ist ein Fehler aufgetreten. "
                "Bitte versuche es später erneut oder kontaktiere den Administrator."
            )
        except:
            pass

# ===================================================================
# FASTAPI APP & LIFESPAN MANAGEMENT
# ===================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application Lifespan Manager für FastAPI"""
    logger.info("=" * 60)
    logger.info("🚀 STARTE TELEGRAM BOT 2026")
    logger.info(f"📁 Konfiguration: {CONFIG_SOURCE}")
    logger.info(f"🔧 Modus: {'PRODUCTION' if IS_PRODUCTION else 'ENTWICKLUNG'}")
    logger.info(f"🤖 Bot Token: {'✅' if BOT_TOKEN else '❌ FEHLT'}")
    logger.info(f"📊 Google Sheets: {'✅' if GOOGLE_CREDENTIALS_BASE64 else '❌'}")
    logger.info(f"👤 Erlaubte User: {ALLOWED_USER_IDS if ALLOWED_USER_IDS else 'Alle'}")
    logger.info("=" * 60)
    
    if not BOT_TOKEN:
        error_msg = "❌ KRITISCHER FEHLER: BOT_TOKEN ist nicht gesetzt!"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        # Bot Application initialisieren
        bot_app = Application.builder().token(BOT_TOKEN).build()
        
        # Handler registrieren
        bot_app.add_handler(CommandHandler("start", start_command))
        bot_app.add_handler(CommandHandler("mysecret", mysecret_command))
        bot_app.add_handler(CommandHandler("status", status_command))
        bot_app.add_handler(MessageHandler(filters.Document.ALL, m3u_handler.process_m3u_document))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
        
        # Error Handler
        bot_app.add_error_handler(error_handler)
        
        # Webhook für Production setzen
        if WEBHOOK_URL and IS_PRODUCTION:
            await bot_app.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info(f"✅ Webhook gesetzt: {WEBHOOK_URL}")
            logger.info("📡 Laufmodus: WEBHOOK")
        else:
            # Polling für Entwicklung
            if not IS_PRODUCTION:
                logger.info("🔄 Laufmodus: POLLING (Entwicklung)")
            else:
                logger.warning("⚠️  Webhook URL nicht gesetzt, aber Production Modus!")
        
        # Bot starten
        await bot_app.initialize()
        await bot_app.start()
        
        # Bot in app state speichern
        app.state.tg_app = bot_app
        app.state.bot_start_time = datetime.now()
        
        logger.info("✅ Bot erfolgreich gestartet")
        logger.info("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Fehler beim Bot-Start: {e}")
        raise
    finally:
        # Cleanup
        logger.info("🛑 Beende Bot...")
        if 'bot_app' in locals():
            try:
                if WEBHOOK_URL and IS_PRODUCTION:
                    await bot_app.bot.delete_webhook()
                await bot_app.stop()
                await bot_app.shutdown()
                logger.info("✅ Bot erfolgreich beendet")
            except Exception as e:
                logger.error(f"❌ Fehler beim Bot-Shutdown: {e}")

# ===================================================================
# FASTAPI APP ERSTELLEN
# ===================================================================
app = FastAPI(
    title="Telegram Bot 2026",
    description="M3U Playlist Processor & Finance Tracker",
    version="2.0.0",
    lifespan=lifespan
)

# ===================================================================
# API ENDPOINTS
# ===================================================================
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    """Webhook Endpoint für Telegram (Production)"""
    if not IS_PRODUCTION:
        return {"error": "Webhook nur im Production-Modus verfügbar"}
    
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
    """Health Check Endpoint für Render/Monitoring"""
    status = {
        "status": "healthy",
        "service": "telegram-bot-2026",
        "timestamp": datetime.now().isoformat(),
        "mode": "production" if IS_PRODUCTION else "development",
        "features": {
            "bot_configured": bool(BOT_TOKEN),
            "google_sheets": bool(GOOGLE_CREDENTIALS_BASE64),
            "m3u_processing": True,
            "webhook_enabled": bool(WEBHOOK_URL and IS_PRODUCTION)
        },
        "config": {
            "source": CONFIG_SOURCE,
            "log_level": LOG_LEVEL,
            "allowed_users_count": len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else "all"
        }
    }
    
    # Bot Laufzeit berechnen
    if hasattr(app.state, 'bot_start_time'):
        uptime = datetime.now() - app.state.bot_start_time
        status["uptime_seconds"] = uptime.total_seconds()
        status["start_time"] = app.state.bot_start_time.isoformat()
    
    return status

@app.get("/")
async def root():
    """Root Endpoint mit Informationen"""
    return {
        "service": "Telegram Bot 2026",
        "version": "2.0.0",
        "description": "M3U Playlist Processor & Finance Tracker",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "webhook": f"/webhook/{{secret}}"
        },
        "mode": "production" if IS_PRODUCTION else "development",
        "timestamp": datetime.now().isoformat()
    }

# ===================================================================
# START SCRIPT (NUR FÜR ENTWICKLUNG)
# ===================================================================
if __name__ == "__main__" and not IS_PRODUCTION:
    # Dieser Block wird NUR in der lokalen Entwicklung ausgeführt
    # In Production (Render) wird Gunicorn verwendet
    
    import uvicorn
    import sys
    
    print("\n" + "=" * 60)
    print("💻 ENTWICKLUNGSMODUS")
    print("=" * 60)
    
    if not BOT_TOKEN:
        print("❌ FEHLER: BOT_TOKEN ist nicht gesetzt!")
        print("Bitte setze die Umgebungsvariable oder erstelle local.py")
        sys.exit(1)
    
    print("🚀 Starte Bot im POLLING Modus...")
    print("📡 Webhook wird NICHT verwendet")
    print(f"🔗 Health Check: http://localhost:8000/health")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
