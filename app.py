import os
import sys
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

# === OpenAI SDK (совместим с Groq OpenAI-compatible API) ===
from openai import OpenAI

# =========================
# ENV & GLOBALS
# =========================
load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()  # @username или numeric (-100xxxxxxxxxx)

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()            # допускаем sk_* и gsk_*
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip()          # для Groq: https://api.groq.com/openai/v1

POST_HOUR = int(os.getenv("POST_HOUR", "12"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))

WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()  # https://<service>.onrender.com
PORT = int(os.getenv("PORT", "8080"))

TZ = ZoneInfo("Asia/Tashkent")

SIGN_RU = "— AI-ассистент канала"
SIGN_UZ = "— Kanalning AI yordamchisi"

# Тематические “пилоны” для разнообразия
CONTENT_PILLARS = [
    "Практические советы по производству и качеству кукурузных палочек",
    "Маркетинг и упаковка снеков: как выделиться и повысить продажи",
    "Истории закулисья бренда и ценности команды",
    "Faktlar va tahlillar: O‘zbekiston va Markaziy Osiyodagi snek bozori",
    "Qiziqarli mini-ideyalar: trendlar, savollar, jamoa faolligi"
]

STYLE_RU = (
    "Коротко и по делу, 2–4 предложения, дружелюбно. Один чёткий инсайт/польза. "
    "Без воды. Можно 1 уместный эмодзи. В конце мягкий CTA."
)
STYLE_UZ = (
    "Qisqa va aniq, 2–4 gap, do'stona ohang. Bitta aniq foydali fikr. "
    "Suvsiz va mavhumliksiz. Istasak 1 emoji. Oxirida yumshoq CTA."
)

# =========================
# VALIDATION & CLIENT
# =========================
def _fail(msg: str) -> None:
    print(f"[FATAL] {msg}", file=sys.stderr)
    raise RuntimeError(msg)

if not BOT_TOKEN:
    _fail("BOT_TOKEN не задан.")
if not CHANNEL_ID:
    _fail("CHANNEL_ID не задан. Пример: @your_channel или -100xxxxxxxxxx.")
# для Groq ключи начинаются с gsk_, у OpenAI — sk_. Принимаем любой непустой.
if not OPENAI_API_KEY:
    _fail("OPENAI_API_KEY не задан.")

# Инициализация OpenAI-клиента (с поддержкой кастомного BASE_URL — Groq и т.п.)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL if OPENAI_BASE_URL else None
)

# =========================
# CONTENT GENERATION
# =========================
def build_bilingual_prompt() -> tuple[str, str]:
    import random
    topic = random.choice(CONTENT_PILLARS)
    system = (
        "Ты — редактор Telegram-канала бренда снеков в Узбекистане. "
        "Готовь ЕЖЕДНЕВНЫЕ лаконичные посты без воды."
    )
    user = f"""
Сгенерируй один компактный пост на тему: “{topic}”.

Точный формат ответа (без заголовков и префиксов):

[RUS]
(2–4 очень коротких предложения. {STYLE_RU})
(до 3 уместных хэштегов максимум)

[UZ]
(2–4 gap, lotin alifbosi. {STYLE_UZ})
(3 tagdan oshma)

Правила:
- RU и UZ формулировки — естественные для каждого языка, не калька.
- Без списков, markdown и ссылок. Эмодзи — только если реально к месту.
- Не добавляй подпись: её я вставлю сам.
"""
    return system, user

def post_signature() -> str:
    return f"\n\n{SIGN_RU}\n{SIGN_UZ}"

async def generate_bilingual_post() -> str:
    """Генерация RU+UZ текста. На ошибках — аккуратный фолбэк."""
    system, user = build_bilingual_prompt()
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.8,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("Пустой ответ от модели")
        return text + post_signature()
    except Exception as e:
        print(f"[OpenAI/Groq ERROR] {e}", file=sys.stderr)
        fallback = (
            "[RUS]\n"
            "Сегодня готовим для вас новый полезный материал про рынок снеков и производство. "
            "Оставайтесь на связи!\n\n"
            "[UZ]\n"
            "Bugun siz uchun snek bozori va ishlab chiqarish bo‘yicha foydali ma’lumot tayyorlayapmiz. "
            "Biz bilan qoling!\n"
        )
        return fallback + post_signature()

# =========================
# TELEGRAM PUBLISHING
# =========================
async def publish_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await generate_bilingual_post()
    try:
        MAX = 4096
        if len(text) <= MAX:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        else:
            parts = [text[i:i+MAX] for i in range(0, len(text), MAX)]
            for i, p in enumerate(parts):
                await context.bot.send_message(chat_id=CHANNEL_ID, text=p if i == 0 else f"(продолжение)\n\n{p}")
    except TelegramError as te:
        print(f"[Telegram ERROR] {te}", file=sys.stderr)
    except Exception as e:
        print(f"[SEND ERROR] {e}", file=sys.stderr)

# =========================
# COMMANDS
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я ежедневный авто-постер RU+UZ.\n"
        "Команды:\n"
        "/postnow — опубликовать RU+UZ пост сейчас\n"
        "/status — текущие настройки\n"
        "/diag — диагностика LLM\n"
        "/help — помощь"
    )

async def postnow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Готовлю RU+UZ пост…")
    try:
        await publish_post(context)
        await update.message.reply_text("Готово ✅")
    except Exception as e:
        await update.message.reply_text(f"Ошибка публикации: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = "webhook" if WEBHOOK_URL else "polling"
    t = f"{POST_HOUR:02d}:{POST_MINUTE:02d}"
    await update.message.reply_text(
        f"Канал: {CHANNEL_ID}\n"
        f"Модель: {OPENAI_MODEL}\n"
        f"BASE_URL: {OPENAI_BASE_URL or 'default'}\n"
        f"Режим: {mode}\n"
        f"Ежедневный пост: {t} (Asia/Tashkent)\n"
        f"Подпись: всегда RU+UZ"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я каждый день публикую один пост на русском и узбекском (lotin). "
        "В конце всегда представляюсь как AI-ассистент.\n\n"
        "Команды: /postnow, /status, /diag, /help"
    )

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диагностика LLM: маскированный ключ, модель, base_url и тестовый ping."""
    masked = (OPENAI_API_KEY[:3] + "..." + OPENAI_API_KEY[-4:]) if OPENAI_API_KEY else "—"
    base = OPENAI_BASE_URL or "default"
    try:
        test = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            max_tokens=5,
        )
        ok = (test.choices[0].message.content or "").strip()
        await update.message.reply_text(
            f"Diag:\nKEY: {masked}\nMODEL: {OPENAI_MODEL}\nBASE_URL: {base}\nOK ✅ ({ok[:60]})"
        )
    except Exception as e:
        await update.message.reply_text(
            f"Diag:\nKEY: {masked}\nMODEL: {OPENAI_MODEL}\nBASE_URL: {base}\nERR: {e}"
        )

# =========================
# SCHEDULER
# =========================
def schedule_daily(app: Application):
    if app.job_queue is None:
        _fail(
            "JobQueue недоступен. Установи зависимость: python-telegram-bot[job-queue,webhooks]==21.4"
        )
    # уберём дубликаты при рестартах
    for job in app.job_queue.get_jobs_by_name("daily_post_tashkent"):
        job.schedule_removal()
    app.job_queue.run_daily(
        publish_post,
        time=time(hour=POST_HOUR, minute=POST_MINUTE, tzinfo=TZ),
        name="daily_post_tashkent",
    )

# =========================
# MAIN
# =========================
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("postnow", postnow_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("diag", diag_cmd))

    schedule_daily(application)

    if WEBHOOK_URL:
        # Webhooks режим для Render
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=f"{BOT_TOKEN}",                    # секретный путь
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",   # публичный URL
        )
    else:
        # Локальная отладка
        application.run_polling()

if __name__ == "__main__":
    main()
