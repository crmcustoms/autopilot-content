# -*- coding: utf-8 -*-
"""
Додає в базу «Джерела новин» офіційний блог Planfix (planfix.ru та planfix.com).
Існуючі джерела не видаляються — їх можна зробити неактивними через Статус = «Неактивний» в Notion.
Запуск: python scripts/add_planfix_sources.py
Потрібен .env: NOTION_TOKEN; NOTION_DATABASE_IDS.json.
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


def get_existing_rss_urls(token, database_id):
    """Повертає множину RSS URL, які вже є в базі."""
    urls = set()
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion_request(token, "POST", "/databases/" + database_id + "/query", body)
        for r in data.get("results", []):
            u = r.get("properties", {}).get("RSS URL", {}).get("url")
            if u:
                urls.add(u.rstrip("/"))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return urls


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN у .env відсутній")
        sys.exit(1)
    ids = load_db_ids()
    db_id = ids["news_sources"]

    existing_urls = get_existing_rss_urls(token, db_id)

    # Джерела Planfix: оф. блог RU та EN
    sources = [
        ("Planfix — оф. блог (planfix.ru)", "https://planfix.ru/blog/feed/"),
        ("Planfix — блог (planfix.com)", "https://planfix.com/blog/feed/"),
    ]

    for name, url in sources:
        url_norm = url.rstrip("/")
        if url_norm in existing_urls:
            print("Пропущено (вже є):", name)
            continue
        try:
            notion_request(token, "POST", "/pages", {
                "parent": {"database_id": db_id},
                "properties": {
                    "Назва": {"title": [{"type": "text", "text": {"content": name}}]},
                    "RSS URL": {"url": url},
                    "Статус": {"select": {"name": "Активний"}},
                },
            })
            print("OK: додано —", name)
            existing_urls.add(url_norm)
        except Exception as e:
            print("Помилка", name[:30], ":", e)
    print("Готово. Джерела не видаляються — неактивні вмикай через Статус «Неактивний» в Notion.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
