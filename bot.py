import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
from datetime import datetime, timedelta

# Настройки
ADMIN_CHAT_ID = -783911087 # ID чата для репортов
MAX_WARNS = 5                   # Макс. кол-во предупреждений
BAN_DURATION = timedelta(hours=1) # Длительность бана

# Инициализация
bot = Bot(token="943989049:AAHjmtOWN3ayL1bLXj5d5-MVL_0CpIdTBqs")
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# База данных (временная)
users_db = {}  # {user_id: {"warns": 0}}
reports_db = []  # Список репортов

# ========== КОМАНДЫ ========== #

@dp.message(Command("start", "help"))
async def cmd_help(message: types.Message):
    """Список всех команд"""
    help_text = """
<b>📜 Доступные команды:</b>

<u>Для всех:</u>
• /help - Справка по командам
• /call - Призвать всех участников
• /report - Пожаловаться на пользователя

<u>Для модераторов:</u>
• /warn - Выдать предупреждение
• /ban - Забанить пользователя
• /mod - Меню модератора
"""
    await message.answer(help_text, parse_mode="HTML")

# ========== СИСТЕМА ПРИЗЫВОВ ========== #

@dp.message(Command("call"))
async def call_members(message: types.Message):
    """Призыв всех участников чата"""
    try:
        members = []
        async for member in bot.get_chat_members(message.chat.id):
            if not member.user.is_bot:
                members.append(member.user.mention_html())
        
        if not members:
            return await message.answer("В чате нет участников для призыва!")
        
        call_msg = "🔔 <b>Внимание!</b> " + " ".join(members[:50])  # Ограничение на 50 упоминаний
        await message.answer(call_msg, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка призыва: {e}")
        await message.answer("Не удалось сделать призыв. Боту нужны права админа!")

# ========== СИСТЕМА РЕПОРТОВ ========== #

@dp.message(Command("report"))
async def report_user(message: types.Message):
    """Отправка жалобы в чат модерации"""
    if not message.reply_to_message:
        return await message.answer("ℹ️ Ответьте на сообщение для жалобы!")
    
    reported_user = message.reply_to_message.from_user
    reporter = message.from_user
    reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Не указана"
    
    # Формируем сообщение для админов
    report_text = (
        f"🚨 <b>Новая жалоба</b>\n\n"
        f"• На: {reported_user.mention_html()}\n"
        f"• ID: <code>{reported_user.id}</code>\n"
        f"• От: {reporter.mention_html()}\n"
        f"• Чат: <code>{message.chat.title}</code>\n"
        f"• Причина: {reason}\n"
        f"• Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
    )
    
    # Кнопки действий для модераторов
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Выдать варн", callback_data=f"warn_{reported_user.id}"),
            InlineKeyboardButton(text="🛑 Забанить", callback_data=f"ban_{reported_user.id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить", callback_data="dismiss")
        ]
    ])
    
    try:
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=report_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        await message.reply("✅ Ваша жалоба отправлена модераторам!")
        reports_db.append({
            "reported_user": reported_user.id,
            "reporter": reporter.id,
            "reason": reason,
            "date": datetime.now()
        })
    except Exception as e:
        logger.error(f"Ошибка отправки репорта: {e}")
        await message.reply("❌ Не удалось отправить жалобу")

# ========== СИСТЕМА ВАРНОВ ========== #

@dp.callback_query(F.data.startswith("warn_"))
async def warn_user(callback: types.CallbackQuery):
    """Выдача предупреждения через кнопку"""
    user_id = int(callback.data.split("_")[1])
    
    # Инициализация записи о пользователе
    if user_id not in users_db:
        users_db[user_id] = {"warns": 0}
    
    users_db[user_id]["warns"] += 1
    warn_count = users_db[user_id]["warns"]
    
    if warn_count >= MAX_WARNS:
        try:
            await bot.ban_chat_member(
                chat_id=callback.message.chat.id,
                user_id=user_id,
                until_date=datetime.now() + BAN_DURATION
            )
            await callback.message.edit_text(
                f"🚷 Пользователь {user_id} забанен (5/5 варнов)",
                reply_markup=None
            )
        except Exception as e:
            await callback.answer(f"Ошибка бана: {e}", show_alert=True)
    else:
        await callback.message.edit_text(
            f"⚠️ Пользователь {user_id} получил предупреждение ({warn_count}/{MAX_WARNS})",
            reply_markup=None
        )
    await callback.answer()

import sqlite3
conn = sqlite3.connect('bot.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS warns
                  (user_id INTEGER PRIMARY KEY, count INTEGER)''')

# ========== ЗАПУСК БОТА ========== #

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
