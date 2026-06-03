import os
import requests
import asyncio

import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
import json

import logging

# simple logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
conn = sqlite3.connect("database1.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_seen TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    event TEXT,
    created_at TEXT
)
""")
conn.commit()


def add_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?)",
        (user_id, datetime.now().isoformat()),
    )
    conn.commit()


def add_event(user_id, event):
    cursor.execute(
        "INSERT INTO events (user_id, event, created_at) VALUES (?, ?, ?)",
        (user_id, event, datetime.now().isoformat()),
    )
    conn.commit()


GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def analyze_order(text: str):
    if not GROQ_API_KEY:
        return {"error": "NO_API_KEY"}

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
You are a senior freelance software engineer and proposal strategist.

Return ONLY valid JSON:

{{
  "analysis": {{
    "summary": "",
    "complexity": "easy|medium|hard",
    "key_points": [],
    "risks": [],
    "suggested_stack": [],
    "clarifying_questions": []
  }},
  "proposals": {{
    "fast": "",
    "professional": "",
    "premium": ""
  }}
}}

Project:
{text}
"""

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1200
    }

    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)

        if r.status_code != 200:
            return {"error": "api", "details": r.text}

        result = r.json()
        content = result["choices"][0]["message"]["content"]

        return {"content": content}

    except Exception as e:
        return {"error": str(e)}
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN not found in environment")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment")

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
states = {}


@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀to unpack the order", callback_data="order")]
        ]
    )
    await message.answer(
        "👋 Hi!\n\n"
        "I will help quickly analyze the order and prepare a strong response.\n\n"
        "What you will get:\n"
        "• What is important to the client\n"
        "• Which questions are worth clarifying\n"
        "• A ready-made response to send\n\n"
        "Click the button below and paste the order text.",
        reply_markup=kb,
    )
    add_user(message.from_user.id)
    add_event(message.from_user.id, "start")


@router.callback_query(lambda c: c.data == "order")
async def button(callback: CallbackQuery):
    user_id = callback.from_user.id
    states[user_id] = {"step": "process", "processing": False}
    await callback.message.answer(
        "📋 Send the order description in a single message.\n\n"
        "I will analyze the requirements, highlight the main points, and prepare a response draft."
    )
    add_event(user_id, "click_order")
    await callback.answer()


@router.callback_query(lambda c: c.data in ["fast", "pro", "premium"])
async def choose(call: CallbackQuery):
    user_id = call.from_user.id
    state = states.get(user_id, {})
    if state.get("step") != "done":
        await call.answer("Сначала отправь заказ")
        return

    proposals = state.get("proposals")
    if not proposals:
        await call.answer("Нет предложений, сначала отправь заказ")
        return

    if call.data == "fast":
        text = proposals.get("fast")
        if not text:
            await call.answer("Этот вариант не был сгенерирован")
            return
    elif call.data == "pro":
        text = proposals.get("professional")
        if not text:
            await call.answer("Этот вариант не был сгенерирован")
            return
    elif call.data == "premium":
        text = proposals.get("premium")
        if not text:
            await call.answer("Этот вариант не был сгенерирован")
            return
    else:
        return

    await call.message.answer(text)
    await call.answer()


@router.message(Command("states12"))
async def stat(message: Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("""SELECT COUNT(*)FROM events WHERE event='start'""")
    start = cursor.fetchone()[0]

    cursor.execute("""SELECT COUNT(*)FROM events WHERE event='click_order'""")
    click_order = cursor.fetchone()[0]

    cursor.execute("""SELECT COUNT(*)FROM events WHERE event='send_order'""")
    send_order = cursor.fetchone()[0]

    cursor.execute("""SELECT COUNT(*)FROM events WHERE event='success'""")
    success = cursor.fetchone()[0]

    await message.answer(
        f"📊 STATISTICS\n\n"
        f"Users: {users}\n"
        f"Start: {start}\n"
        f"Click order: {click_order}\n"
        f"Send order: {send_order}\n"
        f"Success: {success}"
    )


@router.message()
async def mai(message: Message):
    user_id = message.from_user.id
    if not message.text:
        return
    if user_id not in states:
        # If user used /start but didn't press the inline "order" button,
        # allow them to send the order directly by entering process mode.
        states[user_id] = {"step": "process", "processing": False}

    state = states.get(user_id, {})

    if state.get("step") != "process":
        return

    if state.get("processing"):
        return

    # mark as processing in our state store
    state["processing"] = True
    states[user_id] = state
    try:
        add_event(user_id, "send_order")
        loading = await message.answer("🔍 Analyzing the order...")

        result = await asyncio.to_thread(analyze_order, message.text)

        # handle analyze_order structured result
        if isinstance(result, dict) and result.get("error"):
            add_event(user_id, "ai_error")
            await loading.edit_text(f"⚠️ AI service error: {result.get('error')} {result.get('status','')}")
            return

        content = result.get("content") if isinstance(result, dict) else result

        # empty or non-text protection
        if not content or not isinstance(content, str):
            await loading.edit_text("⚠️ AI вернул пустой ответ")
            return

        # basic cleanup before JSON parsing
        content = content.strip()
        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1]
            else:
                content = parts[-1]

        try:
            parsed = json.loads(content)
        except Exception:
            snippet = content[:1000].replace('\n', ' ')
            await loading.edit_text(f"⚠️ AI вернул не JSON. RAW: {snippet}")
            return

        if not parsed.get("proposals"):
            add_event(user_id, "no_proposals")
            keys = ",".join(sorted(parsed.keys())) if isinstance(parsed, dict) else str(type(parsed))
            await loading.edit_text(f"⚠️ AI не смог подготовить отклики. Parsed keys: {keys}")
            return

        # Save analysis and proposals in states for later callback handling
        states[user_id] = {
            "step": "done",
            "processing": False,
            "analysis": parsed.get("analysis", {}),
            "proposals": parsed.get("proposals", {}),
        }

        add_event(user_id, "success")

        analysis = states[user_id]["analysis"]
        summary = analysis.get("summary", "(нет)")
        risks = analysis.get("risks", [])
        if isinstance(risks, list):
            risks_text = "\n- ".join(risks) if risks else "(нет)"
        else:
            risks_text = str(risks)

        complexity = analysis.get("complexity", "(не указано)")
        key_points = analysis.get("key_points", [])
        suggested_stack = analysis.get("suggested_stack", [])
        clarifying_questions = analysis.get("clarifying_questions", [])

        kp_text = "\n- ".join(key_points) if key_points else "(нет)"
        stack_text = ", ".join(suggested_stack) if suggested_stack else "(не указано)"
        q_text = "\n- ".join(clarifying_questions) if clarifying_questions else "(нет)"

        text = f"""
📊 Анализ заказа

📌 Суть:
{summary}

⚠️ Риски:
- {risks_text}

🧠 Сложность: {complexity}

📌 Ключевые моменты:
- {kp_text}

🛠 Рекомендуемый стек: {stack_text}

❓ Вопросы клиенту:
- {q_text}
"""

        await loading.edit_text("Готово — смотри анализ ниже:")
        await message.answer(text)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚡ Быстрый", callback_data="fast")],
                [InlineKeyboardButton(text="💼 Профи", callback_data="pro")],
                [InlineKeyboardButton(text="💰 Премиум", callback_data="premium")],
            ]
        )

        await message.answer("Выбери вариант отклика:", reply_markup=kb)
    finally:
        try:
            states[user_id]["processing"] = False
        except Exception:
            pass


dp.include_router(router)


async def main():
    # ensure no webhook is set (prevents TelegramConflictError on deployments)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
