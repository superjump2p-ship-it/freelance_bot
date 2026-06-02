import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
import json
import requests
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


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def analyze_order(text: str):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "openai/gpt-4.1-mini",
        "messages": [
            {
                "role": "system",
                "content": """ROLE:
You are a senior freelance software engineer and AI assistant that helps freelancers win jobs.

You do TWO things:
1) Analyze client request (business + technical understanding)
2) Prepare 3 different proposal drafts for different strategies

IMPORTANT:
You must NOT output final formatted text for client.
You must return STRICT JSON ONLY.

---

OUTPUT FORMAT (STRICT JSON):

{
  "analysis": {
    "summary": "",
    "risks": [],
    "complexity": "easy | medium | hard",
    "key_points": [],
    "suggested_stack": [],
    "clarifying_questions": []
  },
  "proposals": {
    "fast": "",
    "professional": "",
    "premium": ""
  }
}

---

MEANING OF PROPOSALS:

FAST:
- very short
- direct
- minimal text
- focus on speed + understanding

PROFESSIONAL:
- balanced
- clear structure
- persuasive
- moderate technical detail

PREMIUM:
- senior level tone
- strong engineering reasoning
- architecture thinking
- shows deep understanding of risks and system design
- NO fake real project names
- uses "engineering experience patterns" (e.g. similar systems, not specific companies)

---

RULES:
- Do NOT invent real company/project experience
- Do NOT write markdown
- Do NOT add explanations outside JSON
- Keep text natural and human
- Be specific to the user's request
- Language must match user input language


PROPOSAL STYLE CONTROL:

Each proposal must adapt based on these 3 dimensions:

1) COMMUNICATION TONE:
- friendly
- neutral professional
- confident senior

2) POSITIVITY LEVEL:
- low (strict, technical)
- medium (balanced)
- high (very friendly, client-oriented)

3) LONG-TERM ORIENTATION:
- low: focus only on this task
- medium: mention maintainability
- high: emphasize long-term collaboration and support

IMPORTANT:
These attributes must NOT be explicitly labeled in output.
They must be naturally embedded in the writing style.

Always aim to make the client feel:
- easy to work with
- confident in developer
- safe to continue long-term cooperation


STYLE DISTRIBUTION RULE:

FAST:
- tone: neutral professional
- positivity: medium
- long-term: low

PROFESSIONAL:
- tone: friendly or neutral professional
- positivity: medium-high
- long-term: medium

PREMIUM:
- tone: confident senior
- positivity: high
- long-term: high

---

GOAL:
Help freelancer understand the project AND win the client.
Use communication tone, positivity level, and long-term orientation naturally depending on proposal type (fast / professional / premium).
CRITICAL RULE:
Return ONLY valid JSON. No text before or after JSON.
""",
            },
            {"role": "user", "content": text},
        ],
    }

    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
    except requests.RequestException:
        return {"error": "network"}

    if r.status_code != 200:
        logger.error("OPENROUTER ERROR %s: %s", r.status_code, r.text)
        return {"error": "api", "status": r.status_code, "body": r.text}

    try:
        resp = r.json()
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        logger.error("NOT JSON OR PARSE ERROR: %s", r.text)
        return {"error": "parse", "body": r.text}

    return {"content": content}

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN not found in environment")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in environment")

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
    states[user_id] = "process"
    await callback.message.answer(
        "📋 Send the order description in a single message.\n\n"
        "I will analyze the requirements, highlight the main points, and prepare a response draft."
    )
    add_event(user_id, "click_order")
    await callback.answer()


@router.callback_query(lambda c: c.data in ["fast", "pro", "premium"])
async def choose(call: CallbackQuery):
    user_id = call.from_user.id

    if user_id not in states or not isinstance(states[user_id], dict):
        await call.answer("Сначала отправь заказ")
        return

    proposals = states[user_id].get("proposals")
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
    if getattr(message, "processing", False):
        return
    message.processing = True
    if not message.text:
        return
    if user_id not in states:
        await message.answer("👆Click the button above to start to disassemble.")
        return

    if states.get(user_id) != "process":
        return

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
        await loading.edit_text("⚠️ AI вернул не JSON (просто повтори запрос)")
        return

    if not parsed.get("proposals"):
        add_event(user_id, "no_proposals")
        await loading.edit_text("⚠️ AI не смог подготовить отклики.")
        return

    # Save analysis and proposals in states for later callback handling
    states[user_id] = {
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

    # finish processing
    message.processing = False


dp.include_router(router)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
