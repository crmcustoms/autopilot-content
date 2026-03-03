# Що додати після підключення

Структура Notion і що запускати — **NOTION_STRUCTURE.md**, що підключено/не підключено — **ЗАПУСК_І_СЕРВІСИ.md**.

## 1. .env

Вже є: NOTION_TOKEN, NOTION_PARENT_PAGE_ID, TELEGRAM_BOT_TOKEN, GOOGLE_AI_KEY_1…5. За потреби: ANTHROPIC_API_KEY для /strategy.

## 2. Notion

- **Дублікати баз** — зайві «Контент-кути» / «Контент-план» видалити вручну (Move to trash). Детально: **NOTION_SETUP.md**.
- **Графік** — у базі Контент-план додай вид Calendar або Board (NOTION_SETUP.md).
- **Стратегія та 50 книг** — якщо ще порожні, запусти `python scripts/seed_bases_initial.py` ще раз.

## 3. Бот

Запуск: `python -m bot.bot`. Команди: /start, /plan, /today, /strategy.

## 4. Опційно (пізніше)

Cloudflare R2, Replicate — за потреби.
