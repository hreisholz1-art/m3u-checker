"""
DEPLOY.PY - Production configuration for Render
This file contains all environment-specific settings for deployment.
"""

import os

# ===== RENDER PRODUCTION SETTINGS =====
# These settings are optimized for Render deployment

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "production-secret-key-2026")

# Google Sheets integration
GOOGLE_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")

# Webhook URL (Render provides this automatically)
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# Application settings
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

# Logging level for production
LOG_LEVEL = "INFO"

# Security settings
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "").split(",") if os.getenv("ALLOWED_USER_IDS") else []

# M3U combiner settings (reduced for production safety)
M3U_MAX_WORKERS = 4
M3U_TIMEOUT_SECONDS = 10

# Validation
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is required!")

if not GOOGLE_CREDENTIALS_BASE64:
    print("⚠️  GOOGLE_CREDENTIALS_BASE64 not set. Finance features will be disabled.")

print("✅ Deploy configuration loaded successfully")
print(f"   - Bot Token: {'✓' if BOT_TOKEN else '✗'}")
print(f"   - Google Sheets: {'✓' if GOOGLE_CREDENTIALS_BASE64 else '✗ (finance disabled)'}")
print(f"   - Webhook URL: {WEBHOOK_URL[:50] + '...' if WEBHOOK_URL and len(WEBHOOK_URL) > 50 else WEBHOOK_URL}")