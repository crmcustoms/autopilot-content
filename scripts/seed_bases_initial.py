# -*- coding: utf-8 -*-
"""
Заповнення баз початковими текстами через Gemini (ротація ключів).
- Стратегія/ICP: 1 сторінка (проблема + ICP з 7 кутів).
- Бібліотека книг: топ-50 бізнес-книг (назва + автор).
- Джерела новин: 5–10 RSS для CRM/бізнесу.
- Контент-план: 7 записів-заглушок по одному на буферну тему (без дати).
Потрібен .env: NOTION_TOKEN, GOOGLE_AI_KEYS або GOOGLE_AI_KEY_1..5; NOTION_DATABASE_IDS.json.
При 429 робить паузу 60 с і повторює спробу один раз.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.ai_rotate import get_google_keys_from_env, call_gemini_rotate


def load_env():
    env_path = os.path.join(ROOT, ".env")
    with open(env_path, "r", encoding="utf-8") as f:
        env = {}
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        return env


def load_db_ids():
    with open(os.path.join(ROOT, "NOTION_DATABASE_IDS.json"), "r", encoding="utf-8") as f:
        return json.load(f)


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
        raise RuntimeError(f"Notion {e.code}: {body_err}") from e


def rt(text, max_len=2000):
    if not text:
        return []
    text = str(text)[:max_len]
    return [{"type": "text", "text": {"content": text}}]


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN у .env відсутній")
        sys.exit(1)
    keys = get_google_keys_from_env(env)
    if not keys:
        print("Додай GOOGLE_AI_KEYS у .env")
        sys.exit(1)
    ids = load_db_ids()

    # 1) Стратегія/ICP — одна сторінка
    prompt_strategy = """Дай один короткий блок тексту для Notion (українською):
1) Головна проблема ніші CRM для малого бізнесу в Україні (2–3 речення).
2) Таблицю ICP у вигляді тексту: хто / що хочуть / що стопорить / як говорять / тригери. Без зайвого вступу."""
    try:
        try:
            text = call_gemini_rotate(keys, prompt_strategy)
        except RuntimeError as e:
            if "429" in str(e):
                time.sleep(60)
                text = call_gemini_rotate(keys, prompt_strategy)
            else:
                raise
        notion_request(token, "POST", "/pages", {
            "parent": {"database_id": ids["strategy"]},
            "properties": {
                "Назва": {"title": [{"type": "text", "text": {"content": "Стратегічна база (початкова)"}}]},
                "Проблема": {"rich_text": rt(text[:2000])},
                "ICP": {"rich_text": rt(text)},
            },
        })
        print("OK: Стратегія/ICP — 1 сторінка")
    except Exception as e:
        print("Стратегія/ICP:", e)

    # 2) Бібліотека книг — 50 книг
    prompt_books = """Виведи список рівно 50 бізнес-книг для власників малого бізнесу. Формат кожного рядка: Назва книги | Автор
Тільки список, без нумерації та коментарів. Українською або англійською назви."""
    try:
        try:
            text = call_gemini_rotate(keys, prompt_books)
        except RuntimeError as e:
            if "429" in str(e):
                time.sleep(60)
                text = call_gemini_rotate(keys, prompt_books)
            else:
                raise
        lines = [s.strip() for s in text.strip().split("\n") if "|" in s][:50]
        for line in lines:
            parts = line.split("|", 1)
            name = parts[0].strip()[:2000]
            author = parts[1].strip()[:2000] if len(parts) > 1 else ""
            notion_request(token, "POST", "/pages", {
                "parent": {"database_id": ids["books"]},
                "properties": {
                    "Назва": {"title": [{"type": "text", "text": {"content": name}}]},
                    "Автор": {"rich_text": rt(author)},
                },
            })
        print("OK: Бібліотека книг —", len(lines), "записів")
    except Exception as e:
        print("Бібліотека книг:", e)

    # 3) Джерела новин — фіксований список RSS
    sources = [
        ("DOU Календар", "https://dou.ua/calendar/feed/"),
        ("Mind.ua", "https://mind.ua/rss/all"),
        ("Економічна правда", "https://www.epravda.com.ua/rss/"),
    ]
    for name, url in sources:
        try:
            notion_request(token, "POST", "/pages", {
                "parent": {"database_id": ids["news_sources"]},
                "properties": {
                    "Назва": {"title": [{"type": "text", "text": {"content": name}}]},
                    "RSS URL": {"url": url},
                    "Статус": {"select": {"name": "Активний"}},
                },
            })
        except Exception as e:
            print("Джерело", name, ":", e)
    print("OK: Джерела новин —", len(sources), "записів")

    # 4) Контент-план — 7 записів по буферним темах (заглушки)
    themes = [
        "Пн — Кейс / результат",
        "Вт — Порада / лайфхак CRM",
        "Ср — Біль ЦА / провокація",
        "Чт — Новина / AI для бізнесу",
        "Пт — Порівняння / міф vs реальність",
        "Сб — Особисте / за лаштунками",
        "Нд — Переказ книги",
    ]
    for t in themes:
        try:
            notion_request(token, "POST", "/pages", {
                "parent": {"database_id": ids["content_plan"]},
                "properties": {
                    "Назва": {"title": [{"type": "text", "text": {"content": "Буфер: " + t[:50]}}]},
                    "Статус": {"select": {"name": "Ідея"}},
                    "Тип": {"select": {"name": "Піст"}},
                    "Буферна тема": {"select": {"name": t}},
                    "Платформи": {"multi_select": [{"name": "Telegram"}]},
                },
            })
        except Exception as e:
            if "could not find" in str(e).lower() or "Буферна" in str(e):
                print("Поле Буферна тема ще немає — спочатку запусти setup_schedule_and_buffer.py")
            else:
                print("Контент-план запис", t[:20], ":", e)
    print("OK: Контент-план — 7 буферних записів (заглушки)")
    print("Готово. Перевір бази в Notion.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
