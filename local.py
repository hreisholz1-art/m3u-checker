"""
LOCAL.PY - Local development configuration (COMMENTED TEMPLATE)
Uncomment and modify for local testing.

TO USE LOCALLY:
1. Copy this file to local.py (uncommented)
2. Fill in your actual values
3. Import in telegrambot2026.py instead of deploy.py
"""

# import os

# # ===== LOCAL DEVELOPMENT SETTINGS =====
# # These settings are for local testing

# # Bot configuration - GET FROM @BotFather
# BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual token

# # Webhook settings (for local testing with ngrok)
# WEBHOOK_SECRET = "local-test-secret-2026"
# RENDER_EXTERNAL_URL = None  # Not needed for local polling

# # Google Sheets - Base64 encoded service account JSON
# # Generate with: base64 -w0 your-service-account.json
# GOOGLE_CREDENTIALS_BASE64 = "YOUR_BASE64_CREDENTIALS_HERE"

# # Webhook URL for local testing (if using ngrok)
# # WEBHOOK_URL = "https://xxxx-xx-xx-xx-xx.ngrok-free.app/webhook/..."

# # Application settings
# WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
# WEBHOOK_URL = None  # Use polling locally

# # Logging level for development
# LOG_LEVEL = "DEBUG"

# # Security - Add your Telegram user ID
# ALLOWED_USER_IDS = [123456789]  # Your Telegram user ID

# # M3U combiner settings (faster for local testing)
# M3U_MAX_WORKERS = 2
# M3U_TIMEOUT_SECONDS = 5

# print("✅ Local configuration loaded (DEVELOPMENT MODE)")