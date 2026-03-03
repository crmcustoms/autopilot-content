# -*- coding: utf-8 -*-
"""
Додає 12 промптів з TZ_v2.2 (розділ 4) у базу Notion «Бібліотека промптів».
Запуск: python scripts/fill_prompts_notion.py
"""
import json
import os
import urllib.request
import urllib.error

PROMPTS = [
    ("strategy_base", "Промпт #1 — Стратегічна база", """Ти - контент-стратег. Перед тим, як відповідати, задай мені питання про:
  - ціль, цільову аудиторію, болі, обмеження, тон, платформи

На основі відповідей сформулюй одну головну проблему в моїй ніші,
яку люди реально готові обговорювати і шерити. Дай:
  • чому ця проблема важлива (2–3 чітких речення)
  • цілі контенту на 30 днів (збереження/ліди)
  • таблицю ICP: хто / що хочуть / що їх стопорить /
    як вони говорять / тригери / табу

Без води, конкретно."""),
    ("strategy_angles", "Промпт #2 — 7 кутів теми", """Візьми головну проблему і дай 7 неочевидних кутів:
контрінтуїтивні, "ви робите це неправильно",
міф vs реальність, прихована ціна стандартного рішення.

По кожному: 2 хуки (≤12 слів) + інсайт (≤80 слів) +
факт для довіри + спірне твердження.
Кути не повторюються."""),
    ("strategy_posts", "Промпт #3 — 21 підтема + формати", """По кожному з 7 кутів — 3 підтеми з ефектом
"блін, я про це навіть не думав".

По кожній підтемі — 3 формати:
1. НАВЧАЛЬНИЙ: хук + інсайт + 3 кроки
2. ПРОВОКАЦІЙНИЙ: хук + 3 аргументи + питання
3. КЕЙС: контекст + дії + цифри + висновок"""),
    ("strategy_calendar", "Промпт #4 — Календар 30 днів", """По кожному формату адаптуй під Threads / Reels / Telegram.
Постав метрику успіху. Збери контент-календар на 30 днів:
дата → платформа → тема → формат → ціль → дистрибуція.
Без повторів. Чергування тем. Макс 2 продажних/тиждень.
Формат: JSON масив."""),
    ("article_crm_pain", "Стаття блог/кейс", """Ти — Максим, власник CRMCUSTOMS, 10+ років автоматизації в Україні.
Стаття на тему "{TOPIC}" для crmcustoms.com.

Структура: заголовок (цифра/проблема) → вступ (гачок) →
3-5 розділів з реальними прикладами → CTA на аудит.
Цифри з кейсів (BMW X5 = 180К/міс). Без банальностей.
Мова: українська. 800-1200 слів.

SEO окремим блоком: Title / Description / Keywords / Slug."""),
    ("post_telegram", "Пост Telegram", """Голос каналу @prodayslonakume. Тема: {TOPIC}.
Структура: emoji+заголовок → тіло → порада → CTA.
Telegram Markdown. Короткі абзаци. 100-250 слів.
ЦА: власники бізнесу 35-55 років, Україна."""),
    ("post_linkedin", "Пост LinkedIn", """Ти — Максим з CRMCUSTOMS. Тема: {TOPIC}.
Гачок ≤150 символів → проблема → інсайт → CTA + хештеги.
Без "радий повідомити". Від першої особи. 150-300 слів."""),
    ("news_rewrite", "Рерайт новини", """Перепиши новину від імені Максима.
ОРИГІНАЛ: {NEWS_TEXT} | ДЖЕРЕЛО: {SOURCE_URL}

Дай: короткий пост (150-200 слів) + повний текст (400-600 слів) + SEO.
НЕ копіюй. Переосмислюй. ОБОВ'ЯЗКОВО видаляй всі RU-сервіси
та бренди, заміняй на західні/українські аналоги."""),
    ("case_study", "Написання кейсу", """Напиши кейс за даними {CASE_DATA}.
Заголовок = цитата або результат (НЕ "Кейс CompanyName").
Структура: клієнт → проблема (з цифрами) → рішення (інструменти) →
результати (до/після) → цитата → CTA.
Як розповідь, не звіт. 600-900 слів."""),
    ("book_summary", "Переказ книги", """Щотижневий пост для @prodayslonakume.
Книга: {BOOK_TITLE} — {BOOK_AUTHOR}

КНИГА ТИЖНЯ → Головна ідея → 5 думок з прив'язкою до CRM →
Як я використовую з клієнтами → Оцінка X/10 → Для кого.
250-350 слів."""),
    ("content_plan_gen", "Генерація плану", """Контент-план на 30 днів для @prodayslonakume.
Бізнес: CRMCUSTOMS (Planfix, n8n, Telegram-боти). ЦА: власники 3-50 осіб, Україна.
Розподіл: 4 кейси + 6 порад + 4 новини + 4 болі + 3 книги +
3 порівняння + 3 особисте + 3 Q&A.
JSON: {day, date, type, topic, headline, platforms, priority}.
Без повторів тем/7 днів. Макс 2 продажних/тиждень."""),
    ("image_infographic", "SVG інфографіка", """SVG інфографіка "До/Після" для кейсу.
Дані: {CASE_METRICS}
1200×630px. Ліво ДО #C62828, право ПІСЛЯ #2E7D32.
Arial, мінімалізм, великі цифри, логотип CRMCUSTOMS знизу.
Тільки валідний SVG."""),
    ("video_bomba_raketa", "Сценарій «Бомба-ракета»", """Сценарій для TikTok/Reels/Shorts рубрики «Бомба-ракета».
Кейс: {CASE_DATA}

Персонаж: Максим — впевнений інтегратор якому набридли «зошитники».
Говорить розмовно, зверхній до проблеми але не до клієнта.
Референс: канал «Румянцев Про».

СТРУКТУРА 45-60 сек:
[0-5]   ГАК — клієнт + стан справ. Без вступів.
[5-12]  ПРОБЛЕМА — шокуюча деталь. Емоційний момент.
[12-30] ЩО ЗРОБИВ — по тижнях, називати Planfix/n8n/Telegram-бот.
[30-45] РЕЗУЛЬТАТ — 1-2 конкретні цифри. Несподіваний інсайт.
[45-55] ЕМОЦІЙНА ТОЧКА — одне речення від клієнта.
[55-60] ФІНАЛ — дні + інструменти + цифра.

Фінальна фраза:
  "Що там складного." — складні проекти
  "Все просто. Якщо правильно налаштовано." — швидкі запуски

Вимоги: рубані речення, цифри словами, три крапки для пауз,
тільки українська. Без жаргону та самопохвали.

Після сценарію: заголовок посту + гачок + 5 хештегів."""),
]

CHUNK_SIZE = 2000  # Notion rich_text limit per segment


def _rich_text_chunks(text):
    out = []
    for i in range(0, len(text), CHUNK_SIZE):
        out.append({"type": "text", "text": {"content": text[i : i + CHUNK_SIZE]}})
    return out


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        raise FileNotFoundError("Файл .env не знайдено")
    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def notion_request(token, method, path, body=None):
    url = "https://api.notion.com/v1" + path
    headers = {
        "Authorization": "Bearer " + token,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Notion API {e.code}: {body_err}") from e


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        raise ValueError("NOTION_TOKEN у .env")
    ids_path = os.path.join(os.path.dirname(__file__), "..", "NOTION_DATABASE_IDS.json")
    with open(ids_path, "r", encoding="utf-8") as f:
        ids = json.load(f)
    db_id = ids["prompts"]

    for prompt_id, title, text in PROMPTS:
        body = {
            "parent": {"database_id": db_id},
            "properties": {
                "Назва": {"title": [{"type": "text", "text": {"content": title}}]},
                "ID промпту": {"rich_text": [{"type": "text", "text": {"content": prompt_id}}]},
                "Текст": {"rich_text": _rich_text_chunks(text)},
            },
        }
        notion_request(token, "POST", "/pages", body)
        print("OK:", prompt_id)

    print("\nГотово: 12 промптів додано в Бібліотеку промптів.")


if __name__ == "__main__":
    main()
