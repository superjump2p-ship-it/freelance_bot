"""
db.py - Работа с базой данных SQLite

Таблица reminders:
- id: уникальный идентификатор
- user_id: ID пользователя в Telegram
- text: текст напоминания
- send_at: время отправки (ISO формат)
- done: 0 или 1 (выполнено или нет)
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# Путь к файлу БД
DB_PATH = Path(__file__).parent / "reminders.db"


def init_db():
    """Создаёт таблицу reminders если её нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            send_at TEXT,
            done INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def save_reminder(user_id, text):
    """Сохраняет новое напоминание в БД

    Аргументы:
        user_id: ID пользователя
        text: текст напоминания

    Возвращает:
        ID созданной записи
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO reminders (user_id, text, send_at, done) VALUES (?, ?, NULL, 0)",
        (user_id, text),
    )

    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return reminder_id


def set_send_time(reminder_id, send_at):
    """Сохраняет время отправки напоминания

    Аргументы:
        reminder_id: ID напоминания
        send_at: время в ISO формате (например: "2026-05-20 15:30:00")
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE reminders SET send_at = ? WHERE id = ?", (send_at, reminder_id)
    )

    conn.commit()
    conn.close()


def get_reminder(reminder_id):
    """Получает напоминание по ID

    Возвращает:
        Кортеж (id, user_id, text, send_at, done) или None
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, user_id, text, send_at, done FROM reminders WHERE id = ?",
        (reminder_id,),
    )

    result = cursor.fetchone()
    conn.close()

    return result


def get_active_reminders(user_id):
    """Получает все активные (неотправленные) напоминания пользователя

    Возвращает:
        Список кортежей (id, user_id, text, send_at, done)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, user_id, text, send_at, done FROM reminders WHERE user_id = ? AND done = 0 ORDER BY send_at",
        (user_id,),
    )

    results = cursor.fetchall()
    conn.close()

    return results


def get_due_reminders():
    """Получает все напоминания, которые нужно отправить прямо сейчас

    Возвращает:
        Список кортежей (id, user_id, text, send_at, done)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        "SELECT id, user_id, text, send_at, done FROM reminders WHERE done = 0 AND send_at IS NOT NULL AND send_at <= ?",
        (now,),
    )

    results = cursor.fetchall()
    conn.close()

    return results


def mark_done(reminder_id):
    """Отмечает напоминание как выполненное

    Аргументы:
        reminder_id: ID напоминания
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))

    conn.commit()
    conn.close()
