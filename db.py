"""
db.py

Простое JSON-хранилище напоминаний.

Структура файла `reminders.json`:
{
  "next_id": 1,
  "reminders": {
    "<user_id>": [ {"id":1, "text":"...", "send_at": "ISO or null"}, ... ]
  },
  "pending_custom": { "<chat_id>": reminder_id }
}

API совместимо с остальным кодом: `init_db`, `save_message`, `save_send_time`,
`get_reminder`, `get_active_reminders`, `get_inbox_reminders`,
`set/get/pop_pending_custom`, `get_due_reminders`, `remove_reminder`.
"""

from pathlib import Path
import json
from typing import Optional
from datetime import datetime
import logging

JSON_PATH = Path(__file__).parent / "reminders.json"


def _load() -> dict:
    if not JSON_PATH.exists():
        return {"next_id": 1, "reminders": {}, "pending_custom": {}}
    try:
        with JSON_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logging.exception("Failed to load reminders.json, starting empty")
        return {"next_id": 1, "reminders": {}, "pending_custom": {}}


def _save(data: dict) -> None:
    tmp = JSON_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(JSON_PATH)


def init_db() -> None:
    data = _load()
    # ensure keys exist
    if "next_id" not in data:
        data["next_id"] = 1
    if "reminders" not in data:
        data["reminders"] = {}
    if "pending_custom" not in data:
        data["pending_custom"] = {}
    _save(data)


def save_message(user_id: int, text: str) -> int:
    data = _load()
    nid = data.get("next_id", 1)
    rem = {"id": nid, "text": text, "send_at": None}
    uid = str(user_id)
    data.setdefault("reminders", {}).setdefault(uid, []).append(rem)
    data["next_id"] = nid + 1
    _save(data)
    logging.getLogger("db").info(
        "Saved reminder id=%s for user=%s text=%s",
        nid,
        user_id,
        (text[:50] + "...") if len(text) > 50 else text,
    )
    return nid


def save_send_time(reminder_id: int, send_at_iso: str) -> None:
    data = _load()
    found = False
    for uid, lst in data.get("reminders", {}).items():
        for r in lst:
            if r.get("id") == reminder_id:
                r["send_at"] = send_at_iso
                found = True
                break
        if found:
            break
    if found:
        _save(data)
    else:
        logging.getLogger("db").warning(
            "save_send_time: reminder id=%s not found", reminder_id
        )


def get_reminder(reminder_id: int) -> Optional[tuple]:
    data = _load()
    for uid, lst in data.get("reminders", {}).items():
        for r in lst:
            if r.get("id") == reminder_id:
                return (r["id"], int(uid), r.get("text"), r.get("send_at"))
    return None


def get_active_reminders(user_id: int) -> list[tuple]:
    data = _load()
    uid = str(user_id)
    rows = []
    for r in data.get("reminders", {}).get(uid, []):
        rows.append((r["id"], user_id, r.get("text"), r.get("send_at"), 0))
    return rows


def get_inbox_reminders() -> list[tuple]:
    data = _load()
    rows = []
    for uid, lst in data.get("reminders", {}).items():
        for r in lst:
            rows.append((r["id"], int(uid), r.get("text"), r.get("send_at"), 0))

    # sort by send_at where None goes to end
    def keyfn(x):
        s = x[3]
        return (s is None, s)

    return sorted(rows, key=keyfn)


def set_pending_custom(chat_id: int, reminder_id: int) -> None:
    data = _load()
    data.setdefault("pending_custom", {})[str(chat_id)] = reminder_id
    _save(data)


def get_pending_custom(chat_id: int) -> Optional[int]:
    data = _load()
    val = data.get("pending_custom", {}).get(str(chat_id))
    return int(val) if val is not None else None


def pop_pending_custom(chat_id: int) -> Optional[int]:
    data = _load()
    pc = data.get("pending_custom", {})
    key = str(chat_id)
    val = pc.pop(key, None)
    if val is not None:
        _save(data)
        return int(val)
    return None


def remove_reminder(reminder_id: int) -> bool:
    data = _load()
    for uid, lst in list(data.get("reminders", {}).items()):
        newlst = [r for r in lst if r.get("id") != reminder_id]
        if len(newlst) != len(lst):
            data["reminders"][uid] = newlst
            _save(data)
            return True
    return False


def get_due_reminders(now_dt: datetime) -> list[tuple]:
    """Return list of (id, user_id, text, send_at_iso) where send_at <= now_dt."""
    data = _load()
    out = []
    for uid, lst in data.get("reminders", {}).items():
        for r in lst:
            send = r.get("send_at")
            if send is None:
                continue
            try:
                dt = datetime.fromisoformat(send)
            except Exception:
                logging.getLogger("db").warning(
                    "Invalid send_at for id=%s: %s", r.get("id"), send
                )
                continue
            if dt <= now_dt:
                out.append((r.get("id"), int(uid), r.get("text"), send))
    return out
