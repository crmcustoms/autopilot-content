# -*- coding: utf-8 -*-
"""
1) Додає в базу «Контент-план» поле «Буферна тема» (7 днів тижня).
2) Створює сторінку «Графік публікацій» з посиланням на Контент-план (Calendar/Board по даті та темах).
Запуск: python scripts/setup_schedule_and_buffer.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


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


BUFFER_THEMES = [
    "Пн — Кейс / результат",
    "Вт — Порада / лайфхак CRM",
    "Ср — Біль ЦА / провокація",
    "Чт — Новина / AI для бізнесу",
    "Пт — Порівняння / міф vs реальність",
    "Сб — Особисте / за лаштунками",
    "Нд — Переказ книги",
]


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    parent_id = env.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent_id:
        print("Потрібні NOTION_TOKEN та NOTION_PARENT_PAGE_ID у .env")
        sys.exit(1)
    ids = load_db_ids()
    content_plan_id = ids["content_plan"]

    # 1) Додати поле «Буферна тема» в Контент-план
    try:
        notion_request(token, "PATCH", "/databases/" + content_plan_id, {
            "properties": {
                "Буферна тема": {
                    "select": {
                        "options": [{"name": t} for t in BUFFER_THEMES],
                    },
                },
            },
        })
        print("OK: поле «Буферна тема» додано в Контент-план")
    except Exception as e:
        if "duplicate" in str(e).lower() or "already" in str(e).lower():
            print("Поле «Буферна тема» вже існує")
        else:
            raise

    # 2) Сторінка «Графік публікацій» з посиланням на базу
    db_url = f"https://www.notion.so/{content_plan_id.replace('-', '')}"
    page_body = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "icon": {"type": "emoji", "emoji": "📅"},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": "Графік публікацій"}}]},
        },
    }
    page = notion_request(token, "POST", "/pages", page_body)
    page_id = page["id"]
    notion_request(token, "PATCH", "/blocks/" + page_id + "/children", {
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Відкрий базу «Контент-план» за посиланням нижче. Додай вид Calendar (по полю Дата) або Board (по Буферна тема), щоб бачити графік і переходити до текстів постів."}},
                    ],
                },
            },
            {"object": "block", "type": "bookmark", "bookmark": {"url": db_url}},
        ],
    })
    print("OK: сторінка «Графік публікацій» створена (з посиланням на Контент-план)")


if __name__ == "__main__":
    main()
