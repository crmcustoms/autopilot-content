# -*- coding: utf-8 -*-
"""
Присвоює кожній базі Notion унікальну назву (емодзі + текст), щоб не плутати.
Запуск: python scripts/fix_notion_db_names.py
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


def notion_patch(token, database_id, body):
    url = "https://api.notion.com/v1/databases/" + database_id
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


TITLES = {
    "content_angles": "📐 Контент-кути",
    "content_plan": "📋 Контент-план",
    "strategy": "🎯 Стратегія / ICP",
    "prompts": "🔖 Бібліотека промптів",
    "books": "📚 Бібліотека книг",
    "news_sources": "🌐 Джерела новин",
    "competitors": "🏆 Конкуренти",
    "stats": "📊 Статистика",
    "media": "🖼️ Медіа-бібліотека",
}


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN у .env відсутній")
        sys.exit(1)
    ids = load_db_ids()
    for key, title in TITLES.items():
        if key not in ids:
            continue
        notion_patch(token, ids[key], {"title": [{"type": "text", "text": {"content": title}}]})
        print("OK:", key)
    print("Назви баз оновлено.")


if __name__ == "__main__":
    main()
