"""
db.py

Модуль работы с SQLite без ORM.

Блоки в файле:
- инициализация БД и создание таблицы reminders;
- функции для сохранения текста напоминания и установки времени отправки.

Требования соблюдены: используем стандартный модуль `sqlite3`.
"""

import sqlite3
from pathlib import Path
from typing import Optional
import logging

# Путь к файлу базы данных (в той же папке проекта)
DB_PATH = Path(__file__).parent / "reminders.db"


def get_connection() -> sqlite3.Connection:
    """Возвращает соединение sqlite3 с включённым foreign keys.

    Соединение настраивается так, чтобы результаты были возвращены как обычные кортежи.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Инициализирует базу данных: создаёт таблицу reminders при необходимости.

    Столбцы таблицы reminders:
    - id: INTEGER PRIMARY KEY AUTOINCREMENT
    - user_id: INTEGER — идентификатор пользователя/чата
    - text: TEXT — текст напоминания
    - send_at: TEXT — время отправки в ISO-формате (или NULL)
    - done: INTEGER — флаг выполнения (0 или 1)
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        send_at TEXT,
        send_ts INTEGER,
        done INTEGER NOT NULL DEFAULT 0
    )
    """
    conn = get_connection()
    try:
        conn.executescript(create_table_sql)
        # Если старый файл БД уже существовал без колонки send_ts, добавим её
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(reminders)")
        cols = [r[1] for r in cur.fetchall()]
        if "send_ts" not in cols:
            try:
                cur.execute("ALTER TABLE reminders ADD COLUMN send_ts INTEGER")
            except Exception:
                # Игнорируем, если не удалось добавить (например, concurrent access)
                pass
        conn.commit()
    finally:
        conn.close()


def save_message(user_id: int, text: str) -> int:
    """Сохраняет текст напоминания и возвращает id созданной записи.

    Аргументы:
    - user_id: идентификатор пользователя/чата
    - text: текст напоминания

    Возвращает: id новой записи (int)
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO reminders (user_id, text) VALUES (?, ?)", (user_id, text)
        )
        conn.commit()
        rid = cur.lastrowid
        logging.getLogger("db").info(
            "Saved reminder id=%s for user=%s text=%s",
            rid,
            user_id,
            (text[:50] + "...") if len(text) > 50 else text,
        )
        return rid
    finally:
        conn.close()


def save_send_time(reminder_id: int, send_at_iso: str) -> None:
    """Устанавливает время отправки для записи с заданным id.

    - reminder_id: id записи в таблице reminders
    - send_at_iso: строка времени в ISO-формате (например, '2026-05-17T20:00:00')
    """
    # Преобразуем ISO-строку в целочисленный таймстамп для корректного сравнения в SQLite
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(send_at_iso)
        ts = int(dt.timestamp())
    except Exception:
        ts = None

    conn = get_connection()
    try:
        if ts is not None:
            conn.execute(
                "UPDATE reminders SET send_at = ?, send_ts = ?, done = 0 WHERE id = ?",
                (send_at_iso, ts, reminder_id),
            )
        else:
            conn.execute(
                "UPDATE reminders SET send_at = ?, send_ts = NULL, done = 0 WHERE id = ?",
                (send_at_iso, reminder_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_reminder(reminder_id: int) -> Optional[tuple]:
    """Возвращает запись напоминания (id, user_id, text, send_at, done) или None."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, text, send_at, done FROM reminders WHERE id = ?",
            (reminder_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def get_active_reminders(user_id: int) -> list[tuple]:
    """Возвращает список активных (не выполненных) напоминаний для пользователя.

    Каждый элемент — кортеж `(id, user_id, text, send_at, done)`.
    Результат сортируется по `send_at`, при этом записи без `send_at` идут в конец.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, text, send_at, done
            FROM reminders
            WHERE user_id = ? AND done = 0
            ORDER BY (send_at IS NULL), send_at
            """,
            (user_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_inbox_reminders() -> list[tuple]:
    """Возвращает все записи, где done = 0, отсортированные по `send_at`.

    Каждый элемент — кортеж `(id, user_id, text, send_at, done)`.
    Записи с NULL `send_at` идут в конец списка.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, text, send_at, done
            FROM reminders
            WHERE done = 0
            ORDER BY (send_at IS NULL), send_at
            """,
        )
        return cur.fetchall()
    finally:
        conn.close()


def mark_done(reminder_id: int) -> None:
    """Помечает запись как выполненную (done = 1)."""
    conn = get_connection()
    try:
        conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()
