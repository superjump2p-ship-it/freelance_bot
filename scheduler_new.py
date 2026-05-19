"""
scheduler.py - Фоновая задача для отправки напоминаний

Каждые 30 секунд:
1. Получаем все напоминания, где send_at <= сейчас и done = 0
2. Отправляем каждое напоминание пользователю
3. Отмечаем как done = 1
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from config import BOT_TOKEN
from db import get_due_reminders, mark_done

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def send_reminder(bot, user_id, reminder_text, reminder_id):
    """Отправляет одно напоминание пользователю

    Аргументы:
        bot: экземпляр Bot
        user_id: ID пользователя в Telegram
        reminder_text: текст напоминания
        reminder_id: ID напоминания в БД
    """
    try:
        message = f"🔔 Напоминание:\n\n{reminder_text}"
        await bot.send_message(user_id, message)
        logger.info(f"Напоминание {reminder_id} отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания {reminder_id}: {e}")


async def process_due_reminders(bot):
    """Обработчик - проверяет и отправляет напоминания

    1. Получает все напоминания из БД, которые пора отправить
    2. Отправляет каждое напоминание
    3. Отмечает как выполненное
    """

    # Получаем напоминания из БД
    reminders = get_due_reminders()

    if not reminders:
        logger.debug("Нет напоминаний для отправки")
        return

    logger.info(f"Найдено {len(reminders)} напоминаний для отправки")

    # Обработаем каждое напоминание
    for reminder_id, user_id, reminder_text, send_at, done in reminders:
        # Отправляем напоминание
        await send_reminder(bot, user_id, reminder_text, reminder_id)

        # Отмечаем как выполненное
        mark_done(reminder_id)
        logger.info(f"Напоминание {reminder_id} отмечено как выполненное")


async def scheduler_loop():
    """Главный цикл планировщика

    Каждые 30 секунд проверяет и отправляет напоминания
    """
    bot = Bot(token=BOT_TOKEN)

    logger.info("Планировщик запущен")

    while True:
        try:
            # Обработаем напоминания
            await process_due_reminders(bot)

            # Ждём 30 секунд
            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
            # Ждём 30 секунд перед следующей попыткой
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
