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
from db import get_connection

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
    now_ts = int(datetime.now().timestamp())
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Используем числовой таймстамп send_ts для надёжных сравнений
        cur.execute(
            "SELECT id, user_id, text FROM reminders WHERE done = 0 AND send_ts IS NOT NULL AND send_ts <= ?",
            (now_ts,),
        )
        rows = cur.fetchall()

        if not rows:
            logging.debug("No due reminders found")

        for reminder_id, user_id, text in rows:
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

                await bot.send_message(
                    user_id, f"⏰ Напоминание\n📩 {text}", reply_markup=markup
                )
                # После отправки очищаем send_at и send_ts, чтобы не слать повторно —
                # дальнейшие действия (snooze/done) будут обновлять запись
                cur.execute(
                    "UPDATE reminders SET send_at = NULL, send_ts = NULL WHERE id = ?",
                    (reminder_id,),
                )
                conn.commit()
                logging.info("Sent reminder %s to user %s", reminder_id, user_id)
            except Exception:
                logging.exception(
                    "Failed to send reminder %s to %s", reminder_id, user_id
                )
    finally:
        conn.close()


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
