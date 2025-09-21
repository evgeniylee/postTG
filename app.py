import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from openai import OpenAI

# === ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")          # @username или numeric (-100xxxxxxxxxx)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

POST_HOUR = int(os.getenv("POST_HOUR", "12"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")    # https://<service>.onrender.com
PORT = int(os.getenv("PORT", "8080"))
TZ = ZoneInfo("Asia/Tashkent")

# === OpenAI client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# Тематические направления (рандомизация)
CONTENT_PILLARS = [
    "Практические советы по производству и качеству кукурузных палочек",
    "Маркетинг и упаковка снеков: как выделиться и повысить продажи",
    "Истории закулисья бренда и ценности команды",
    "Факты и аналитика рынка снеков в Узбекистане va Markaziy Osiyo",
    "Qiziqarli mini-ideyalar: trendlar, savollar va jamoa faolligi"
]

STYLE_RU = (
    "Коротко и по делу, 2–4 предложения, дружелюбно. Один чёткий инсайт/польза. "
    "Без воды и общих фраз. Можно 1 уместный эмодзи. В конце мягкий CTA."
)
STYLE_UZ = (
    "Qisqa va aniq, 2–4 gap, do'stona ohang. Bitta aniq foydali fikr. "
    "Suvsiz va mavhumliksiz. Istasak 1 emoji. Oxirida yumshoq CTA."
)

SIGN_RU = "— AI-ассистент канала"
SIGN_UZ = "— Kanalning AI yordamchisi"

def build_bilingual_prompt():
    import random
    topic = random.choice(CONTENT_PILLARS)
    system = (
        "Ты — редактор Telegram-канала бренда снеков в Узбекистане. "
        "Твоя задача: готовить ЕЖЕДНЕВНЫЕ лаконичные посты без воды."
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
- RU и UZ формулировки естественные для каждого языка, не калька.
- Никаких списков, markdown, ссылок, эмодзи — только если реально к месту.
- Не добавляй подпись: её я вставлю сам.
"""
    return system, user

def post_signature() -> str:
    return f"\n\n{SIGN_RU}\n{SIGN_UZ}"

async def generate_bilingual_post() -> str:
    system, user = build_bilingual_prompt()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        temperature=0.8,
    )
    text = resp.choices[0].message.content.strip()
    # Добавляем подпись (RU+UZ) всегда
    return text + post_signature()

# === Публикация ===
async def publish_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await generate_bilingual_post()
    await context.bot.send_message(chat_id=CHANNEL_ID, text=text)

# === Команды ===
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я ежедневный авто-постер RU+UZ. Команды:\n"
        "/postnow — опубликовать прямо сейчас\n"
        "/status — показать настройки\n"
        "/help — помощь"
    )

async def postnow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Готовлю RU+UZ пост…")
    try:
        await publish_post(context)
        await update.message.reply_text("Готово ✅")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = f"{POST_HOUR:02d}:{POST_MINUTE:02d}"
    await update.message.reply_text(
        f"Канал: {CHANNEL_ID}\n"
        f"Модель: {OPENAI_MODEL}\n"
        f"Ежедневный пост: {t} (Asia/Tashkent)\n"
        f"Подпись: всегда RU+UZ"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я каждый день публикую один пост на русском и узбекском (lotin). "
        "В конце всегда представляюсь как AI-ассистент.\n\n"
        "Команды: /postnow, /status, /help"
    )

def schedule_daily(app: Application):
    app.job_queue.run_daily(
        publish_post,
        time=time(hour=POST_HOUR, minute=POST_MINUTE, tzinfo=TZ),
        name="daily_post_tashkent"
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("postnow", postnow_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    schedule_daily(application)

    # Webhook для Render (если указан URL), иначе — polling
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=f"{BOT_TOKEN}",                    # секретный путь
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",   # публичный URL
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
