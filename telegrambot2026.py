import logging
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from deploy import BOT_TOKEN, WEBHOOK_SECRET
from finance_handler import handle_finance_command
from m3u_handler import handle_m3u_document

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хендлер для текстовых сообщений
@router.message(F.text)
async def handle_text(message: types.Message):
    logger.info(f"Получено текстовое сообщение: {message.text}")
    response = handle_finance_command(message.text)
    if response:
        await message.answer(response)

# Хендлер для документов
@router.message(F.document)
async def handle_document(message: types.Message):
    await handle_m3u_document(message)

# Подключение роутера
dp.include_router(router)

# FastAPI приложение
app = web.Application()
SimpleRequestHandler(dp, bot).register(app, path=f"/webhook/{WEBHOOK_SECRET}")

# Установка вебхука при старте
async def on_startup():
    await bot.set_webhook(f"https://m3u-checker-ccpf.onrender.com/webhook/{WEBHOOK_SECRET}")
    logger.info("Вебхук установлен")

app.on_startup.append(on_startup)
