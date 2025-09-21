# Telegram AI Autoposter (RU + UZ, daily)

Ежедневный автопост RU+UZ в Telegram-канал. В конце поста — подпись AI-ассистента. Команды: `/postnow`, `/status`, `/help`. Вебхуки для Render или локальный polling.

## Быстрый старт (локально)
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Создай `.env` по образцу `.env.example`
4. `python app.py`
5. Добавь бота админом в канал → отправь `/postnow` в ЛС боту → проверь пост

## Деплой на Render
1. Залей репозиторий на GitHub
2. В Render: **New → Web Service → Connect repo**
3. Build: `pip install -r requirements.txt` ; Start: `python app.py`
4. В **Environment** задай переменные:
   - `BOT_TOKEN`
   - `CHANNEL_ID` (`@username` или numeric `-100...`)
   - `OPENAI_API_KEY`
   - (опц.) `OPENAI_MODEL`, `POST_HOUR`, `POST_MINUTE`
5. После первого деплоя возьми URL вида `https://<service>.onrender.com`
6. Добавь `WEBHOOK_URL` = этот URL → Redeploy
7. Проверь `/status` и `/postnow`

## Пояснения
- Часовой пояс — Asia/Tashkent.
- Планировщик: `JobQueue.run_daily(...)`.
- RU/UZ текст генерится через OpenAI Chat Completions.
- Подпись AI-ассистента добавляется принудительно.

## Частые вопросы
- **Numeric chat_id**: сделай бота админом канала, затем `getChat` по `@username` через Bot API — в ответе увидишь `id` вида `-100xxxxxxxxxx`.
- **Два поста в день**: добавь второй `run_daily` с другим временем.
- **Рандомное время**: пересоздавай джоб каждый день со случайным `time(...)`.
