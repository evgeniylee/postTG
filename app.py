import os
import sys
from datetime import time, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

# OpenAI SDK (совместим с Groq OpenAI-compatible API)
from openai import OpenAI

# =========================
# ENV & GLOBALS
# =========================
load_dotenv()

# Основные
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHANNEL_ID = (os.getenv("CHANNEL_ID") or "").strip()  # @username или numeric (-100xxxxxxxxxx)

# LLM / Groq
OPENAI_API_KEY  = (os.getenv("OPENAI_API_KEY") or "").strip()       # допускаем sk_* и gsk_*
OPENAI_MODEL    = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip()       # для Groq: https://api.groq.com/openai/v1

# Время
POST_HOUR   = int(os.getenv("POST_HOUR", "12"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))
TZ = ZoneInfo("Asia/Tashkent")

# Запуск
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()  # https://<service>.onrender.com
PORT        = int(os.getenv("PORT", "8080"))

# Профиль компании (файл/ENV)
BRAND_PROFILE_PATH  = (os.getenv("BRAND_PROFILE_PATH") or "brand_profile.md").strip()
COMPANY_PROFILE_ENV = (os.getenv("COMPANY_PROFILE") or "").strip()

# Оверрайды промтов из ENV (необязательно)
PROMPT_SYSTEM   = (os.getenv("PROMPT_SYSTEM") or "").strip()
PROMPT_STYLE_RU = (os.getenv("PROMPT_STYLE_RU") or "").strip()
PROMPT_STYLE_UZ = (os.getenv("PROMPT_STYLE_UZ") or "").strip()
TOPICS_ENV      = (os.getenv("TOPICS") or "").strip()  # Темы через | (pipe)

# Подпись к постам (фиксировано)
SIGN_RU = "— AI-ассистент канала"
SIGN_UZ = "— Kanalning AI yordamchisi"

# Темы по умолчанию (если не заданы через TOPICS)
CONTENT_PILLARS = [
    "Практические советы по производству и качеству кукурузных палочек",
    "Маркетинг и упаковка снеков: как выделиться и повысить продажи",
    "Истории закулисья бренда и ценности команды",
    "Faktlar va tahlillar: O‘zbekiston va Markaziy Osiyodagi snek bozori",
    "Qiziqarli mini-ideyalar: trendlar, savollar, jamoa faolligi",
    "Как добиться равномерного слоя пудры и сохранить хруст",
    "Qadoqlashning ahamiyati: havo 'yostiqchasi' nimaga kerak?"
]

# Стиль по умолчанию (можно переопределить ENV'ом)
STYLE_RU = (
    "Коротко, по делу и с лёгким юмором. 2–3 уместных эмодзи. "
    "1 факт/лайфхак, мягкий вопрос-CTA в конце. 2–4 релевантных хэштега."
)
STYLE_UZ = (
    "Qisqa va aniq, yengil hazil bilan. 2–3 mos emoji. "
    "1 foydali fikr/fakt, oxirida yumshoq savol-CTA. 2–4 mos hashtag."
)

# =========================
# VALIDATION & HELPERS
# =========================
def _fail(msg: str) -> None:
    print(f"[FATAL] {msg}", file=sys.stderr)
    raise RuntimeError(msg)

def _split_env_list(s: str) -> list[str]:
    return [x.strip() for x in s.split("|") if x.strip()]

if not BOT_TOKEN:
    _fail("BOT_TOKEN не задан.")
if not CHANNEL_ID:
    _fail("CHANNEL_ID не задан. Пример: @your_channel или -100xxxxxxxxxx.")
if not OPENAI_API_KEY:
    _fail("OPENAI_API_KEY не задан (для Groq ключ начинается с gsk_).")

# Применяем ENV-оверрайды для стилей/тем
if PROMPT_STYLE_RU:
    STYLE_RU = PROMPT_STYLE_RU
if PROMPT_STYLE_UZ:
    STYLE_UZ = PROMPT_STYLE_UZ
if TOPICS_ENV:
    CONTENT_PILLARS = _split_env_list(TOPICS_ENV)

# Профиль бренда: файл -> ENV -> пусто
def _read_brand_profile() -> str:
    p = BRAND_PROFILE_PATH
    if p and os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                txt = f.read()
                return txt[:8000]  # ограничим размер для контекста
        except Exception as e:
            print(f"[WARN] brand_profile read error: {e}")
    if COMPANY_PROFILE_ENV:
        return COMPANY_PROFILE_ENV[:8000]
    return ""

BRAND_PROFILE_TEXT = _read_brand_profile()

# LLM client (OpenAI or Groq-compatible)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL if OPENAI_BASE_URL else None,
)

# =========================
# PROMPTS
# =========================
def build_bilingual_prompt() -> tuple[str, str]:
    """Собираем system+user промты. Темы случайно, профиль подмешивается в system."""
    import random
    topic = random.choice(CONTENT_PILLARS)

    # System: берём из ENV если задан, иначе дефолт + профиль компании
    system_default = (
        "Ты — SMM-редактор Telegram-канала про снеки для аудитории Узбекистана. "
        "Пиши ДВУЯЗЫЧНО: сначала RUS, затем UZ (latin). "
        "Тон — дружелюбный, живой, немного юмора; используй 2–3 уместных эмодзи. "
        "В каждом языке дай один интересный факт или мини-лайфхак по теме. "
        "Не выдумывай точные цифры и факты; если не уверен — пиши без чисел. "
        "Не добавляй подпись — её добавит бот."
    )
    system = (PROMPT_SYSTEM or system_default) + (
        f"\n\n=== COMPANY PROFILE START ===\n{BRAND_PROFILE_TEXT}\n=== COMPANY PROFILE END ==="
        if BRAND_PROFILE_TEXT else ""
    )

    style_ru = STYLE_RU
    style_uz = STYLE_UZ

    user = f"""
Sana: {datetime.now(TZ).strftime('%Y-%m-%d')}. Tema/Тема: “{topic}”.

Format javobi / Формат ответа (bez sarlavha/prefixov):

[RUS]
(2–5 предложений; {style_ru})
(2–3 эмодзи по смыслу)
(в конце 2–4 релевантных хэштега)

[UZ]
(2–5 gap; {style_uz})
(2–3 mos emoji)
(oxirida 2–4 hashtag)

Qoidalar / Правила:
- RU va UZ matnlar tabiiy bo‘lsin, literal tarjima emas.
- Statistikani agar aniq bilmasang — sonlarsiz yoz; havola/narx — yo‘q.
- Sog‘liq/politika mavzulariga kirmagin.
- Подпись не добавляй — её вставит бот.
"""
    return system, user

def post_signature() -> str:
    return f"\n\n{SIGN_RU}\n{SIGN_UZ}"

# =========================
# GENERATION & PUBLISH
# =========================
async def generate_bilingual_post() -> str:
    """Генерим RU+UZ текст; на ошибках — аккуратный фолбэк."""
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
        print(f"[LLM ERROR] {e}", file=sys.stderr)
        fallback = (
            "[RUS]\n"
            "Готовим для вас свежий материал о снеках и их хрусте. "
            "Скоро расскажем больше интересных фактов! 😊\n\n"
            "[UZ]\n"
            "Sneklar va ularning xrusti haqida yangi foydali material tayyorlanmoqda. "
            "Tez orada qiziqarli faktlar bilan bo‘lishamiz! 🙂\n"
        )
        return fallback + post_signature()

async def publish_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await generate_bilingual_post()
    try:
        MAX = 4096
        if len(text) <= MAX:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        else:
            parts = [text[i:i+MAX] for i in range(0, len(text), MAX)]
            for i, p in enumerate(parts):
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=p if i == 0 else f"(продолжение)\n\n{p}"
                )
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
        "/status  — текущие настройки\n"
        "/diag    — диагностика LLM\n"
        "/profile — проверить, что профиль бренда подмешивается\n"
        "/help    — помощь"
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
        f"Пост ежедневно: {t} (Asia/Tashkent)\n"
        f"Подпись: всегда RU+UZ"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я каждый день публикую один пост на русском и узбекском (lotin). "
        "В конце всегда представляюсь как AI-ассистент.\n\n"
        "Команды: /postnow, /status, /diag, /profile, /help"
    )

async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ln = len(BRAND_PROFILE_TEXT or "")
    preview = (BRAND_PROFILE_TEXT[:500] + "…") if BRAND_PROFILE_TEXT and len(BRAND_PROFILE_TEXT) > 500 else (BRAND_PROFILE_TEXT or "—")
    await update.message.reply_text(
        f"Профиль бренда загружен: {ln} символов.\n\nПревью:\n{preview}"
    )

# =========================
# SCHEDULER
# =========================
def schedule_daily(app: Application):
    if app.job_queue is None:
        _fail("JobQueue недоступен. Установи: python-telegram-bot[job-queue,webhooks]==21.4")
    # убираем дубликаты при рестартах
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
    application.add_handler(CommandHandler("profile", profile_cmd))

    schedule_daily(application)

    if WEBHOOK_URL:
        # Webhooks режим (Render)
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
