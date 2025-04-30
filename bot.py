import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiogram.enums import ParseMode
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("7943989049:AAHjmtOWN3ayL1bLXj5d5-MVL_0CpIdTBqs")
REPORT_CHAT_ID = os.getenv("-1002323280754")  # ID чата для репортов

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Проверьте .env файл.")

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Инициализация базы данных
def init_db():
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        
        # Таблица с настройками чатов
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            welcome_text TEXT DEFAULT 'Добро пожаловать, {name}!',
            rules_text TEXT DEFAULT 'Правила не установлены',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Таблица с варнами
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            admin_id INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
        )
        """)
        
        conn.commit()

init_db()

# ========== КОМАНДЫ БОТА ========== #

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я сова для управления чатами.\n"
        "📌 Добавьте меня в группу и дайте права администратора для полного функционала.\n"
        "ℹ️ Список команд: /help"
    )

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = """
<b>📋 Основные команды:</b>

<u>Для всех:</u>
/start - Начало работы
/help - Справка по командам
/rules - Правила чата
/report [причина] - Пожаловаться на пользователя (ответом на сообщение)
/warns - Посмотреть свои предупреждения

<u>Для админов:</u>
/set_welcome [текст] - Установить приветствие
/set_rules [текст] - Установить правила
/warn [причина] - Выдать предупреждение (ответом на сообщение)
/unwarn - Снять предупреждение
/call_all - Созвать всех участников
/call [@username] - Созвать конкретного пользователя
"""
    await message.answer(help_text)

# ========== ФУНКЦИИ ПРИВЕТСТВИЯ ========== #

@dp.message(F.new_chat_members)
async def welcome_new_members(message: Message):
    chat_id = message.chat.id
    for new_member in message.new_chat_members:
        if new_member.id == bot.id:
            await message.answer("Спасибо за добавление! Дайте мне.")
            continue
        
        # Получаем текст приветствия из БД
        with sqlite3.connect('bot_db.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT welcome_text FROM chats WHERE chat_id = ?", (chat_id,))
            result = cursor.fetchone()
            welcome_text = result[0] if result else 'Добро пожаловать, {name}!'
        
        welcome_msg = welcome_text.format(
            name=new_member.full_name,
            chat=message.chat.title
        )
        await message.answer(welcome_msg)

# ========== ФУНКЦИИ РЕПОРТОВ ========== #

@dp.message(Command("report"))
@dp.message(F.reply_to_message, Command("report"))
async def report_user(message: Message):
    if not message.reply_to_message:
        await message.reply("ℹ️ Используйте команду /report в ответ на сообщение пользователя, на которого хотите пожаловаться.")
        return
    
    if not REPORT_CHAT_ID:
        await message.reply("⚠️ Функция репортов не настроена администратором.")
        return
    
    reported_user = message.reply_to_message.from_user
    reporter = message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Не указана"
    
    report_text = f"""
🚨 <b>Новый репорт</b> 🚨
Чат: {message.chat.title} (ID: {message.chat.id})
Жалоба на: {reported_user.full_name} (@{reported_user.username}, ID: {reported_user.id})
От: {reporter.full_name} (@{reporter.username}, ID: {reporter.id})
Причина: {reason}
"""
    try:
        await bot.send_message(REPORT_CHAT_ID, report_text)
        await message.reply("✅ Ваша жалоба отправлена администраторам.")
    except Exception as e:
        logger.error(f"Ошибка при отправке репорта: {e}")
        await message.reply("⚠️ Не удалось отправить жалобу. Попробуйте позже.")

# ========== ФУНКЦИИ ВАРНОВ ========== #

@dp.message(Command("warn"), F.reply_to_message)
async def warn_user(message: Message):
    if not await check_admin(message):
        return
    
    warned_user = message.reply_to_message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Не указана"
    
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO warns (chat_id, user_id, admin_id, reason) VALUES (?, ?, ?, ?)",
            (message.chat.id, warned_user.id, message.from_user.id, reason)
        )
        conn.commit()
    
    warn_count = get_warn_count(message.chat.id, warned_user.id)
    await message.reply(
        f"⚠️ Пользователю {warned_user.full_name} выдано предупреждение.\n"
        f"Всего предупреждений: {warn_count}\n"
        f"Причина: {reason}"
    )

@dp.message(Command("unwarn"), F.reply_to_message)
async def unwarn_user(message: Message):
    if not await check_admin(message):
        return
    
    warned_user = message.reply_to_message.from_user
    
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM warns WHERE chat_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1",
            (message.chat.id, warned_user.id)
        )
        conn.commit()
    
    await message.reply(f"✅ Снято одно предупреждение с пользователя {warned_user.full_name}")

@dp.message(Command("warns"))
async def show_warns(message: Message):
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    warn_count = get_warn_count(message.chat.id, user.id)
    
    await message.reply(
        f"ℹ️ Пользователь {user.full_name} имеет {warn_count} предупреждений."
    )

def get_warn_count(chat_id, user_id):
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone()[0]

# ========== ФУНКЦИИ СОЗЫВА ========== #

@dp.message(Command("call_all"))
async def call_all(message: Message):
    if not await check_admin(message):
        return
    
    try:
        chat_members_count = await bot.get_chat_members_count(message.chat.id)
        await message.reply(f"📢 @all Внимание! Созыв всех участников! (Всего: {chat_members_count})")
    except Exception as e:
        logger.error(f"Ошибка при созыве всех: {e}")
        await message.reply("⚠️ Не удалось выполнить созыв всех участников.")

@dp.message(Command("call"))
async def call_user(message: Message):
    if not await check_admin(message):
        return
    
    if len(message.text.split()) < 2:
        await message.reply("ℹ️ Укажите username пользователя после команды, например: /call @username")
        return
    
    username = message.text.split()[1].lstrip('@')
    await message.reply(f"📢 @{username}, вас вызывают!")

# ========== АДМИН КОМАНДЫ ========== #

@dp.message(Command("set_welcome"))
async def set_welcome(message: Message):
    if not await check_admin(message):
        return
    
    welcome_text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    
    if not welcome_text:
        await message.reply("ℹ️ Используйте: /set_welcome [текст]\n"
                          "Доступные переменные: {name} - имя пользователя, {chat} - название чата")
        return
    
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO chats (chat_id, welcome_text) VALUES (?, ?)",
            (message.chat.id, welcome_text)
        )
        conn.commit()
    
    await message.reply("✅ Приветственное сообщение установлено!")

@dp.message(Command("set_rules"))
async def set_rules(message: Message):
    if not await check_admin(message):
        return
    
    rules_text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    
    if not rules_text:
        await message.reply("ℹ️ Используйте: /set_rules [текст правил]")
        return
    
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO chats (chat_id, rules_text) VALUES (?, ?)",
            (message.chat.id, rules_text)
        )
        conn.commit()
    
    await message.reply("✅ Правила чата установлены!")

@dp.message(Command("rules"))
async def show_rules(message: Message):
    with sqlite3.connect('bot_db.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rules_text FROM chats WHERE chat_id = ?",
            (message.chat.id,)
        )
        result = cursor.fetchone()
        rules_text = result[0] if result else "Правила чата не установлены."
    
    await message.reply(f"📜 Правила чата:\n\n{rules_text}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========== #

async def check_admin(message: Message) -> bool:
    """Проверяет, является ли пользователь администратором"""
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ['administrator', 'creator']:
            return True
        
        await message.reply("⚠️ Эта команда доступна только администраторам чата.")
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки админки: {e}")
        return False

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
