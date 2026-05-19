"""
main.py - Главный файл бота на aiogram 3

Логика:
1. Пользователь отправляет сообщение
2. Сохраняем текст в БД
3. Показываем кнопки для выбора времени
4. Пользователь выбирает время
5. Сохраняем время в БД
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import Command

from config import BOT_TOKEN
from db import (
    init_db,
    save_reminder,
    set_send_time,
    get_reminder,
    get_active_reminders,
    mark_done,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== ФУНКЦИИ ОБРАБОТКИ ДЕЙСТВИЙ ==========


def save_text_to_db(user_id, text):
    """Сохраняет текст сообщения в БД и возвращает ID"""
    reminder_id = save_reminder(user_id, text)
    logger.info(f"Сохранено напоминание ID {reminder_id} для пользователя {user_id}")
    return reminder_id


def calculate_time_1hour():
    """Рассчитывает время: сейчас + 1 час"""
    time = datetime.now() + timedelta(hours=1)
    return time.isoformat()


def calculate_time_evening():
    """Рассчитывает время: сегодня в 20:00"""
    now = datetime.now()
    evening = now.replace(hour=20, minute=0, second=0, microsecond=0)

    # Если уже прошли 20:00, то на завтра
    if evening <= now:
        evening = evening + timedelta(days=1)

    return evening.isoformat()


def calculate_time_tomorrow():
    """Рассчитывает время: завтра в 09:00"""
    tomorrow = datetime.now().date() + timedelta(days=1)
    time = datetime.combine(tomorrow, datetime.min.time().replace(hour=9))
    return time.isoformat()


def save_time_to_db(reminder_id, send_at_iso):
    """Сохраняет время отправки в БД"""
    set_send_time(reminder_id, send_at_iso)
    logger.info(f"Сохранено время {send_at_iso} для напоминания {reminder_id}")


def get_reminder_from_db(reminder_id):
    """Получает напоминание из БД"""
    return get_reminder(reminder_id)


def get_user_reminders(user_id):
    """Получает все активные напоминания пользователя"""
    return get_active_reminders(user_id)


def mark_reminder_done(reminder_id):
    """Отмечает напоминание как выполненное"""
    mark_done(reminder_id)
    logger.info(f"Напоминание {reminder_id} отмечено как выполненное")


# ========== ОБРАБОТЧИКИ КОМАНД ==========


async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer("Привет! Отправь мне сообщение, и я напомню о нём позже.")


async def cmd_reminders(message: Message):
    """Обработчик команды /reminders - показывает активные напоминания"""
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id)

    if not reminders:
        await message.answer("У вас нет активных напоминаний.")
        return

    # Формируем список напоминаний
    text = "Ваши активные напоминания:\n\n"
    for reminder_id, user_id, reminder_text, send_at, done in reminders:
        if send_at:
            text += f"📌 {reminder_text}\n⏰ {send_at}\n\n"
        else:
            text += f"📌 {reminder_text}\n⏰ (время не выбрано)\n\n"

    await message.answer(text)


async def handle_text_message(message: Message):
    """Обработчик обычных текстовых сообщений"""
    user_id = message.from_user.id
    text = message.text

    # Сохраняем текст в БД
    reminder_id = save_text_to_db(user_id, text)

    # Создаём кнопки для выбора времени
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ Через 1 час", callback_data=f"time_1h:{reminder_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌙 Сегодня вечером",
                    callback_data=f"time_evening:{reminder_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Завтра утром", callback_data=f"time_tomorrow:{reminder_id}"
                )
            ],
        ]
    )

    await message.answer(
        f'Напоминание сохранено: "{text}"\n\nКогда отправить?', reply_markup=keyboard
    )


async def handle_time_callback(
    callback_query: CallbackQuery, time_type: str, reminder_id: int
):
    """Обработчик выбора времени из кнопок"""

    # Рассчитываем время в зависимости от типа
    if time_type == "1h":
        send_at = calculate_time_1hour()
        label = "⏰ Через 1 час"
    elif time_type == "evening":
        send_at = calculate_time_evening()
        label = "🌙 Сегодня вечером"
    elif time_type == "tomorrow":
        send_at = calculate_time_tomorrow()
        label = "📅 Завтра утром"
    else:
        await callback_query.answer("Ошибка: неизвестное время")
        return

    # Сохраняем время в БД
    save_time_to_db(reminder_id, send_at)

    # Получаем текст напоминания из БД
    reminder = get_reminder_from_db(reminder_id)
    if reminder:
        reminder_text = reminder[2]
    else:
        reminder_text = "(текст не найден)"

    # Показываем подтверждение
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.message.answer(
        f"✅ Напоминание установлено!\n\n"
        f"📌 Текст: {reminder_text}\n"
        f"⏰ Время: {label}"
    )
    await callback_query.answer()


# ========== MAIN FUNCTION ==========


async def main():
    """Главная функция - запускает бота"""

    # Инициализируем БД
    init_db()
    logger.info("База данных инициализирована")

    # Создаём бота и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем обработчик команды /start
    @dp.message(Command("start"))
    async def start_handler(message: Message):
        await cmd_start(message)

    # Регистрируем обработчик команды /reminders
    @dp.message(Command("reminders"))
    async def reminders_handler(message: Message):
        await cmd_reminders(message)

    # Регистрируем обработчик обычных сообщений
    @dp.message()
    async def text_handler(message: Message):
        await handle_text_message(message)

    # Регистрируем обработчик кнопок
    @dp.callback_query()
    async def callback_handler(callback_query: CallbackQuery):
        data = callback_query.data

        # Парсим данные из callback_data
        # Формат: "time_1h:123" или "time_evening:123" и т.д.
        parts = data.split(":")
        if len(parts) != 2:
            await callback_query.answer("Ошибка: неправильные данные")
            return

        time_type = parts[0].replace("time_", "")
        try:
            reminder_id = int(parts[1])
        except ValueError:
            await callback_query.answer("Ошибка: неправильный ID")
            return

        await handle_time_callback(callback_query, time_type, reminder_id)

    # Запускаем polling
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
