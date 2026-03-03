# Бот @crmcontent_bot

Один скрипт, без n8n. Читає контент-план з Notion, відповідає на команди в Telegram.

## Що потрібно

- У корені проекту: `.env` (TELEGRAM_BOT_TOKEN, NOTION_TOKEN), `NOTION_DATABASE_IDS.json`
- Python 3

## Запуск

З кореня проекту («Контент менеджер»):

```bash
python -m bot.bot
```

або

```bash
python bot/bot.py
```

Зупинка: Ctrl+C.

## Команди

| Команда   | Що робить |
|-----------|------------|
| /start   | Привітання та список команд |
| /plan    | План на найближчі 7 днів з Notion (база «Контент-план», поле «Дата») |
| /today   | Що заплановано на сьогодні |
| /strategy| Заглушка (далі — скрипт strategy_runner) |

Інші команди з ТЗ (/news, /drafts, /stats, кнопки затвердження) — наступні кроки.
