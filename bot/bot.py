from functions.file_processing import FileConvertToText  
from telebot.async_telebot import AsyncTeleBot
from config.settings import settings
import datetime
import os


BOT_TOKEN = settings.BOT_API or os.getenv("BOT_API")
bot = AsyncTeleBot(BOT_TOKEN)
UTC = datetime.timezone.utc
pending_feedback = set()
user_state = {}
CHECK_TIMEOUT_SECONDS = 5 * 60
FILES_DIR = "files"
os.makedirs(FILES_DIR, exist_ok=True)

converter = FileConvertToText()
FORMATS = {
    '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp', '.jfif',
    '.docx', '.csv', '.pdf', '.xlsx', '.xls', '.txt' }

MAX_SIZE_BYTES = 10 * 1024 * 1024

CANCEL_VARIANTS = {
    "❌ Отменить / Cancel",
    "❌ Отменить", "Отменить", "отменить",
    "Cancel", "cancel",
    "Бекор кардан", "бекор кардан", "Бекор"
}
