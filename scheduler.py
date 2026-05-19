"""
scheduler.py

Периодический планировщик, который каждые 30 секунд проверяет SQLite
и отправляет пользователям напоминания, у которых пришло время.

Поведение:
- каждые 30 секунд выполняет запрос к таблице `reminders` в базе данных
- ищет записи, где `send_at` <= текущее время и `done = 0`
- отправляет сообщение пользователю и помечает запись как выполненную (`done = 1`)

После отправки сообщение имеет формат:
⏰ Напоминание
📩 {text}

Файл документирован — ниже объяснения всех основных блоков кода.
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from db import get_due_reminders, remove_reminder

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)


async def check_and_send(bot: Bot) -> None:
    """Проверяет БД на просроченные напоминания и отправляет их.

    Алгоритм:
    - берём текущее время в ISO-формате
    - выбираем все записи с `done = 0` и `send_at` не NULL, где `send_at` <= now
    - для каждой записи пытаемся отправить сообщение `bot.send_message`
    - если отправка успешна, помечаем запись `done = 1`
    """
    now = datetime.now()
    rows = get_due_reminders(now)
    if not rows:
        logging.debug("No due reminders found")
    else:
        logging.info("Found %d due reminders", len(rows))
        for r in rows:
            logging.debug("due reminder: %s", r)

    for reminder_id, user_id, text, send_at in rows:
        try:
            # Inline action buttons: done / snooze 1h / snooze tomorrow
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Сделано",
                            callback_data=f"rem_action:{reminder_id}:done",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отложить на 1 час",
                            callback_data=f"rem_action:{reminder_id}:snooze_1h",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отложить на завтра",
                            callback_data=f"rem_action:{reminder_id}:snooze_tomorrow",
                        )
                    ],
                ]
            )

            # Отправляем сообщение и в случае успеха помечаем запись как выполненную
            try:
                # сохраняем возвращённое сообщение для отладки
                sent_msg = await bot.send_message(
                    user_id, f"⏰ Напоминание\n📩 {text}", reply_markup=markup
                )
            except Exception:
                # если отправка упала — логируем и пропускаем обновление БД
                logging.exception(
                    "Failed to send reminder %s to %s", reminder_id, user_id
                )
                continue

            # удаляем напоминание из хранилища после успешной отправки
            try:
                removed = remove_reminder(reminder_id)
                if not removed:
                    logging.getLogger("scheduler").warning(
                        "Sent reminder %s but failed to remove from storage",
                        reminder_id,
                    )
            except Exception:
                logging.exception(
                    "Failed to remove reminder %s after sending", reminder_id
                )
            msg_id = getattr(sent_msg, "message_id", None)
            logging.info(
                "Sent reminder %s to user %s (message_id=%s)",
                reminder_id,
                user_id,
                msg_id,
            )
        except Exception:
            logging.exception("Failed to send reminder %s to %s", reminder_id, user_id)


async def scheduler_loop(interval_seconds: int = 30) -> None:
    """Главная петля планировщика.

    Создаёт экземпляр `Bot` и в цикле вызывает `check_and_send`, затем ждёт
    `interval_seconds`.
    """
    bot = Bot(token=BOT_TOKEN)
    try:
        logging.info("Scheduler started, interval=%s seconds", interval_seconds)
        while True:
            await check_and_send(bot)
            await asyncio.sleep(interval_seconds)
    finally:
        # корректно закрываем HTTP-сессию aiogram/aiohttp
        try:
            await bot.session.close()
        except Exception:
            # на некоторых версиях aiogram этот объект может отличаться,
            # поэтому подавляем исключения при закрытии.
            pass


if __name__ == "__main__":
    try:
        asyncio.run(scheduler_loop())
    except KeyboardInterrupt:
        logging.info("Scheduler stopped by user")
