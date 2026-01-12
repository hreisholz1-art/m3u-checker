import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.types import ContentType
from deploy import BOT_TOKEN, WEBHOOK_SECRET
from finance_handler import handle_finance_command
from m3u_handler import handle_m3u_document

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Хендлер для текстовых сообщений
@dp.message_handler(content_types=ContentType.TEXT)
async def handle_text(message: types.Message):
    logger.info(f"Получено текстовое сообщение: {message.text}")
    response = handle_finance_command(message.text)
    if response:
        await message.answer(response)

# Хендлер для документов
@dp.message_handler(content_types=ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    await handle_m3u_document(message)

# Настройка вебхука
async def on_startup(dp):
    await bot.set_webhook(f"https://m3u-checker-ccpf.onrender.com/webhook/{WEBHOOK_SECRET}")
    logger.info("Вебхук установлен")

if __name__ == "__main__":
    executor.start_webhook(
        dp,
        webhook_path=f"/webhook/{WEBHOOK_SECRET}",
        on_startup=on_startup,
        skip_updates=True,
        host="0.0.0.0",
        port=10000,
    )
