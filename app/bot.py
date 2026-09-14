from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, KeyboardButton, ReplyKeyboardMarkup

from .config import settings

dp = Dispatcher()

BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="🚀 Запуск"),
    BotCommand(command="help", description="❓ Помощь"),
    BotCommand(command="capture", description="💭 Новая мысль"),
    BotCommand(command="ingest", description="📥 Внешний материал"),
    BotCommand(command="ask", description="🔎 Спросить Wiki"),
    BotCommand(command="recent", description="🕘 Последнее"),
    BotCommand(command="status", description="ℹ️ Статус"),
    BotCommand(command="cancel", description="⛔ Отмена"),
]


def create_bot() -> Bot:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан. Заполните .env (см. .env.example).")
    return Bot(token=settings.telegram_bot_token)


def main_keyboard() -> ReplyKeyboardMarkup:
    """Основная клавиатура из ТЗ (Раздел 10)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💭 Новая мысль"), KeyboardButton(text="📥 Ingest")],
            [KeyboardButton(text="🔎 Спросить Wiki"), KeyboardButton(text="🕘 Последнее")],
        ],
        resize_keyboard=True,
    )