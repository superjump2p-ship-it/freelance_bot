import os
import asyncio
import sqlite3
from datetime import datetime

import requests
from aiogram import Bot, Dispatcher, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.filters import CommandStart, Command

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


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def analyze_order(text: str):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": """ROLE:
You are a highly experienced freelance software engineer who regularly wins projects on Upwork, Fiverr, and direct client contracts. Act like a real freelancer writing a proposal to win a job. Your goal is to maximize the chance of being hired.

Key behaviour and responsibilities:
- Think like a senior freelancer, not a chatbot
- Be confident, concise, and practical
- Never sound generic or robotic
- Focus on value, execution, and clarity
- Do not invent requirements that are not mentioned by the client
- Base conclusions only on the provided project description
- Do not assume specific frameworks, databases, or technologies unless mentioned by the client.

FORMAT:
Produce a concise, structured response containing the following sections (use these headings):

1) Client Needs Summary
- Extract the real goal behind the request and the primary success criteria.

2) Key Risks / Complexity
- Identify unclear parts, technical risks, and scaling/architecture concerns.

3) Smart Clarifying Questions
- Ask only high-impact questions that affect cost, scope, or architecture.

4) Proposal
- Write as a real freelancer addressing the client directly: brief understanding, approach (stack/structure/plan), and a clear next step.

5) Estimation
- Difficulty (easy/medium/hard), realistic time range, and a budget range. Note that estimates depend on final scope.

6) Rules and Tone
- Professional but human; confident but not arrogant; do NOT be overly polite or verbose; avoid filler phrases.

LANGUAGE:
- Detect the user's language from the input and respond ONLY in that language. Do not switch languages or insert translations.

Use the structure above exactly.
Keep responses concise, practical, and focused on helping a freelancer understand and win the project.
""",
            },
            {"role": "user", "content": text},
        ],
    }

    r = requests.post(url, json=data, headers=headers)
    if r.status_code != 200:
        return "⚠️ AI service is temporarily unavailable."
    
    try:
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return "Error: AI request failed"


TOKEN = os.getenv("TOKEN")
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


@router.callback_query()
async def button(callback: CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "order":
        states[user_id] = "process"
        await callback.message.answer(
            "📋 Send the order description in a single message.\n\n"
            "I will analyze the requirements, highlight the main points, and prepare a response draft."
        )
    add_event(user_id, "click_order")
    await callback.answer()


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
        await message.answer("👆Click the button above to start to disassemble.")
        return
    if states[user_id] == "process":
        add_event(user_id, "send_order")
        loading = await message.answer("🔍 Analyzing the order...")

        result = await asyncio.to_thread(analyze_order, message.text)
        add_event(user_id, "success")
    
        if len(result) > 4000:
            result = result[:4000]
        await loading.edit_text(result)

        states[user_id] = None


dp.include_router(router)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
