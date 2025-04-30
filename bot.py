import logging
import sqlite3
import os
TOKEN = os.getenv("BOT_TOKEN")
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ChatPermissions
from datetime import datetime, timedelta
from dotenv import load_dotenv


# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token="7943989049:AAHjmtOWN3ayL1bLXj5d5-MVL_0CpIdTBqs")
dp = Dispatcher(bot=bot, storage=MemoryStorage())

# Подключение к SQLite
conn = sqlite3.connect('chat_manager.db')
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''CREATE TABLE IF NOT EXISTS chats
                  (chat_id INTEGER PRIMARY KEY, 
                   welcome_text TEXT,
                   rules_text TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS warns
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   chat_id INTEGER,
                   user_id INTEGER,
                   admin_id INTEGER,
                   reason TEXT,
                   date TIMESTAMP)''')

conn.commit()

# ========== КОМАНДЫ ========== #
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Дай админкку!")

@dp.message(Command("set_welcome"))
async def set_welcome(message: types.Message):
    """Установка приветственного сообщения"""
    if not message.chat.type == "private":
        if await is_admin(message):
            welcome_text = message.text.replace("/set_welcome", "").strip()
            cursor.execute("INSERT OR REPLACE INTO chats VALUES (?, ?, ?)", 
                          (message.chat.id, welcome_text, None))
            conn.commit()
            await message.reply("✅ Приветствие установлено!")

@dp.message(Command("warn"))
async def warn_user(message: types.Message):
    """Выдать предупреждение"""
    if await is_admin(message):
        if message.reply_to_message:
            user = message.reply_to_message.from_user
            reason = message.text.replace("/warn", "").strip()
            
            cursor.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, date) VALUES (?, ?, ?, ?, ?)",
                          (message.chat.id, user.id, message.from_user.id, reason, datetime.now()))
            conn.commit()
            
            # Проверка на 3 предупреждения
            cursor.execute("SELECT COUNT(*) FROM warns WHERE chat_id=? AND user_id=?", 
                         (message.chat.id, user.id))
            warn_count = cursor.fetchone()[0]
            
            if warn_count >= 3:
                await bot.ban_chat_member (
                    chat_id=message.chat.id,
                    user_id=user.id,
                    until_date=datetime.now() + timedelta(hours=1))
                await message.reply(f"🚷 Пользователь {user.full_name} заблокирован на 1 час (3 предупреждения)!")
            else:
                await message.reply(f"⚠ {user.full_name} получил предупреждение ({warn_count}/3). Причина: {reason}")

# ========== ОБРАБОТЧИКИ СОБЫТИЙ ========== #
@dp.message(F.new_chat_members)
async def welcome_new_members(message: types.Message):
    """Приветствие новых участников"""
    cursor.execute("SELECT welcome_text FROM chats WHERE chat_id=?", (message.chat.id,))
    welcome_text = cursor.fetchone()
    
    if welcome_text:
        for user in message.new_chat_members:
            if user.id != bot.id:
                await message.answer(
                    welcome_text[0].replace("{name}", user.full_name),
                    parse_mode="HTML"
                )

# ========== УТИЛИТЫ ========== #
async def is_admin(message: types.Message) -> bool:
    """Проверка прав администратора"""
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["administrator", "creator"]

# Запуск бота
if __name__ == "__main__":
    logger.info("Бот запущен!")
    dp.run_polling(bot)

    load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🤖 Бот запущен на Railway!")

@dp.message(F.text)
async def echo(message: types.Message):
    await message.answer(f"Вы написали: {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())