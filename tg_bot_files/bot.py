import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
import os

# === Настройка ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ACCESS_CODE = os.getenv("ACCESS_CODE")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment (.env). Please add your bot token to .env as BOT_TOKEN=...")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Хранилище данных (в памяти)
authorized_users = set()
# active_reminders: maps user_id -> datetime of next reminder OR True when active without scheduled job yet
active_reminders = {}

# --- Функция для отправки напоминания ---
async def send_reminder(user_id: int):
    # Если пользователь больше не активен — не шлём
    if user_id not in active_reminders:
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Поднял ✅", callback_data="upproduct"),
                InlineKeyboardButton(text="Прекратить напоминание ❌", callback_data="stoptask")
            ]
        ]
    )
    try:
        await bot.send_message(user_id, "📊 Поднимите товар 🔥", reply_markup=keyboard)
    except Exception as e:
        logging.exception("Не удалось отправить напоминание пользователю %s: %s", user_id, e)
        # В случае ошибки — оставляем попытки на следующих запусках

# --- Планирование следующего напоминания ---
def schedule_next_reminder(user_id: int, hours: int = 4):
    job_id = f"reminder_{user_id}"
    next_time = datetime.now() + timedelta(hours=hours)
    # Запланировать или заменить существующую задачу
    scheduler.add_job(
        send_reminder,
        DateTrigger(run_date=next_time),
        args=[user_id],
        id=job_id,
        replace_existing=True
    )
    active_reminders[user_id] = next_time
    logging.info("Scheduled next reminder for %s at %s", user_id, next_time)

# --- Отмена напоминания ---
def cancel_reminder(user_id: int):
    job_id = f"reminder_{user_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    active_reminders.pop(user_id, None)
    logging.info("Cancelled reminders for %s", user_id)

# --- Команда /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Введите код-пароль для доступа к боту🔒")
        return
    await show_start_button(message)

# --- Команды, соответствующие кнопкам (для удобства) ---
@dp.message(commands=["gototask"])
async def cmd_gototask(message: types.Message):
    # Повести себя как кнопка "Да ✅"
    await show_start_button(message)
    # User will press the button to actually start

@dp.message(commands=["upproduct"])
async def cmd_upproduct(message: types.Message):
    # Повести себя как нажатие "Поднял ✅"
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Сначала войдите через код-пароль.")
        return
    schedule_next_reminder(user_id)
    await message.answer("✅ Товар поднят! Следующее напоминание через 4 часа.")

@dp.message(commands=["stoptask"])
async def cmd_stoptask(message: types.Message):
    # Повести себя как нажатие "Прекратить напоминание ❌"
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Сначала войдите через код-пароль.")
        return
    cancel_reminder(user_id)
    await message.answer("❌ Напоминания остановлены. Чтобы запустить снова нажмите 'Начнем?👽' → Да ✅")

# --- Обработка ввода кода (любой текст) ---
@dp.message()
async def check_code(message: types.Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    # Если пользователь уже авторизован — игнорируем этот обработчик
    if user_id in authorized_users:
        return
    if not ACCESS_CODE:
        await message.answer("Код доступа не задан на сервере. Попросите администратора настроить ACCESS_CODE.")
        return
    if text == ACCESS_CODE:
        authorized_users.add(user_id)
        await message.answer("Успешно✅ Вы можете пользоваться ботом📊")
        await show_start_button(message)
    else:
        await message.answer("❌ Неверный код. Попробуйте снова.")

# --- Отправка кнопки "Начнем?👽" ---
async def show_start_button(message_or_callback):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да ✅", callback_data="gototask")]
        ]
    )
    # message_or_callback может быть types.Message или types.CallbackQuery
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer("Начнем?👽", reply_markup=keyboard)
    else:
        # CallbackQuery
        await message_or_callback.message.answer("Начнем?👽", reply_markup=keyboard)

# --- Обработка кнопки "Да ✅" ---
@dp.callback_query(F.data == "gototask")
async def cb_gototask(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in authorized_users:
        await callback.answer("Сначала введите код-пароль.")
        await callback.message.answer("Введите код-пароль для доступа к боту🔒")
        return
    # Включаем напоминания и планируем первое через 4 часа
    schedule_next_reminder(user_id)
    await callback.answer("Отлично! Первое напоминание через 4 часа.")
    try:
        await callback.message.edit_text("🕒 Отлично! Первое напоминание через 4 часа.")
    except Exception:
        pass

# --- Обработка кнопки "Поднял ✅" ---
@dp.callback_query(F.data == "upproduct")
async def cb_upproduct(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in authorized_users:
        await callback.answer("Сначала введите код-пароль.")
        return
    schedule_next_reminder(user_id)
    await callback.answer("Отлично! Следующее напоминание через 4 часа ⏰")
    try:
        await callback.message.edit_text("✅ Товар поднят! Следующее напоминание через 4 часа.")
    except Exception:
        pass

# --- Обработка кнопки "Прекратить напоминание ❌" ---
@dp.callback_query(F.data == "stoptask")
async def cb_stoptask(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in authorized_users:
        await callback.answer("Сначала введите код-пароль.")
        return
    cancel_reminder(user_id)
    await callback.answer("Напоминания остановлены.")
    try:
        await callback.message.edit_text("❌ Напоминания остановлены.")
    except Exception:
        pass
    # Показываем кнопку "Начнем?👽" снова
    await show_start_button(callback)

# --- Запуск ---
async def main():
    scheduler.start()
    logging.info("Scheduler started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
