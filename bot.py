import logging
import sqlite3
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message,InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta


# Настройки
MAX_WARNS = 3                   # Макс. кол-во предупреждений
BAN_DURATION = timedelta(hours=1) # Длительность бана

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                welcome_text TEXT DEFAULT 'Добро пожаловать, {name}!'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                user_id INTEGER,
                chat_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        conn.commit()

init_db()



# 2. Загрузка конфигурации
BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / '.env'
load_dotenv(ENV_PATH)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден в .env файле")

# 3. Создание бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()  # Вот где создается dp!


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========== #

async def check_admin(message: Message) -> bool:
    """Проверяет, является ли пользователь администратором чата"""
    try:
        member = await bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        return False

async def get_warn_count(user_id: int, chat_id: int) -> int:
    """Получает количество предупреждений пользователя"""
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count FROM warns WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        result = cursor.fetchone()
        return result[0] if result else 0

async def add_warn(user_id: int, chat_id: int) -> int:
    """Добавляет предупреждение пользователю"""
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        current = await get_warn_count(user_id, chat_id)
        if current == 0:
            cursor.execute(
                "INSERT INTO warns (user_id, chat_id, count) VALUES (?, ?, 1)",
                (user_id, chat_id)
            )
        else:
            cursor.execute(
                "UPDATE warns SET count = count + 1 WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
        conn.commit()
        return current + 1

# ========== КОМАНДЫ БОТА ========== #

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот. Используй /help для списка команд")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = """
📋 Основные команды:

Для всех:
/help - Справка по командам
/report [причина] - Пожаловаться на пользователя (ответом на сообщение)
/call @username - Созвать конкретного пользователя

Для админов:
/call_all - Созвать всех участников
"""
    await message.answer(help_text)

@dp.message(F.new_chat_members)
async def welcome_new_members(message: Message):
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            await message.answer("Спасибо за добавление! Дайте мне права администратора.")
            continue
        
        with sqlite3.connect('bot_db.db') as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT welcome_text FROM chats WHERE chat_id = ?",
                (message.chat.id,)
            )
            welcome_text = cursor.fetchone()[0] if cursor.fetchone() else 'Добро пожаловать, {name}!'
        
        await message.answer(
            welcome_text.format(name=new_member.full_name, chat=message.chat.title)
        )

# ========== СИСТЕМА ПРИЗЫВОВ ========== #

@dp.message(Command("call_all"))
async def call_all(message: Message):
    if not await check_admin(message):
        return await message.answer("⚠️ Эта команда доступна только администраторам!")
    
    try:
        count = await bot.get_chat_member_count(message.chat.id)
        await message.answer(f"📢 @all Внимание! Всего участников: {count}")
    except Exception as e:
        logger.error(f"Ошибка при созыве всех: {e}")
        await message.answer("⚠️ Не удалось выполнить созыв.")

@dp.message(Command("call"))
async def call_user(message: Message):
    
    if len(message.text.split()) < 2:
        return await message.answer("ℹ️ Укажите username пользователя, например: /call @username")
    
    username = message.text.split()[1].lstrip('@')
    await message.answer(f"📢 @{username}, вас вызывают!")

# ========== СИСТЕМА РЕПОРТОВ ========== #

@dp.message(Command("report"))
async def report_user(message: Message):
    if not message.reply_to_message:
        return await message.answer("ℹ️ Ответьте на сообщение для жалобы!")
    
    if not ADMIN_CHAT_ID:
        return await message.answer("⚠️ Чат для жалоб не настроен.")
    
    reported = message.reply_to_message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Не указана"
    
    report_text = (
        f"🚨 Жалоба от {message.from_user.mention_html()}\n"
        f"👤 На: {reported.mention_html()} (ID: {reported.id})\n"
        f"📝 Причина: {reason}\n"
        f"💬 Чат: {message.chat.title}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Выдать варн", callback_data=f"warn_{reported.id}"),
            InlineKeyboardButton(text="🛑 Забанить", callback_data=f"ban_{reported.id}")
        ],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="dismiss")]
    ])
    
    try:
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=report_text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
        await message.answer("✅ Ваша жалоба отправлена!")
    except Exception as e:
        logger.error(f"Ошибка отправки жалобы: {e}")
        await message.answer("❌ Не удалось отправить жалобу")

# ========== ОБРАБОТКА КНОПОК ========== #

@dp.callback_query(F.data.startswith("warn_"))
async def process_warn(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    chat_id = callback.message.chat.id
    
    warn_count = await add_warn(user_id, chat_id)
    
    if warn_count >= MAX_WARNS:
        try:
            await bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=datetime.now() + BAN_DURATION
            )
            text = f"🚷 Пользователь {user_id} забанен (3/3 варнов)"
        except Exception as e:
            text = f"⚠️ Ошибка бана: {e}"
    else:
        text = f"⚠️ Пользователь {user_id} получил предупреждение ({warn_count}/{MAX_WARNS})"
    
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()

# ========== ЗАПУСК БОТА ========== #

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
