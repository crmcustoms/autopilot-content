# -*- coding: utf-8 -*-
"""
Створення 9 баз Notion за TZ_v2.2 (розділ 5).
Запуск: python scripts/create_notion_databases.py
Потрібен .env з NOTION_TOKEN та NOTION_PARENT_PAGE_ID.
Увага: при повторному запуску створюються дублікати баз — зайві можна видалити в Notion.
"""
import json
import os
import urllib.request
import urllib.error

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        raise FileNotFoundError("Файл .env не знайдено в корені проекту")
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
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Notion API {e.code}: {body}") from e

def create_database(token, parent_id, title, properties):
    body = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    return notion_request(token, "POST", "/databases", body)

def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    parent_id = env.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent_id:
        raise ValueError("У .env потрібні NOTION_TOKEN та NOTION_PARENT_PAGE_ID")

    created = {}

    # 1. Контент-кути (без зв'язків — потрібен для Контент-плану)
    print("1. Контент-кути...")
    db = create_database(token, parent_id, "📐 Контент-кути", {
        "Назва": {"title": {}},
        "Хук": {"rich_text": {}},
        "Інсайт": {"rich_text": {}},
        "Факт": {"rich_text": {}},
        "Твердження": {"rich_text": {}},
    })
    created["content_angles"] = db["id"]
    print("   id:", db["id"])

    # 2. Контент-план (зв'язок «Кут» додамо пізніше через PATCH)
    print("2. Контент-план...")
    db = create_database(token, parent_id, "Контент-план", {
        "Назва": {"title": {}},
        "Статус": {"select": {"options": [
            {"name": "Ідея", "color": "gray"},
            {"name": "Готово", "color": "blue"},
            {"name": "На затвердженні", "color": "yellow"},
            {"name": "Заплановано", "color": "orange"},
            {"name": "Опубліковано", "color": "green"},
        ]}},
        "Тип": {"select": {"options": [
            {"name": "Піст"}, {"name": "Стаття"}, {"name": "Кейс"},
            {"name": "Новина"}, {"name": "Книга"}, {"name": "Відео"},
        ]}},
        "Тема": {"select": {"options": [
            {"name": "CRM"}, {"name": "Planfix"}, {"name": "n8n"},
            {"name": "AI"}, {"name": "Бізнес"}, {"name": "Особисте"},
        ]}},
        "Платформи": {"multi_select": {"options": [
            {"name": "Telegram"}, {"name": "LinkedIn"}, {"name": "Facebook"},
            {"name": "Instagram"}, {"name": "Сайт"},
        ]}},
        "Дата": {"date": {}},
        "Текст посту": {"rich_text": {}},
        "Текст статті": {"rich_text": {}},
        "SEO Title": {"rich_text": {}},
        "SEO Description": {"rich_text": {}},
        "SEO Keywords": {"rich_text": {}},
        "SEO Slug": {"rich_text": {}},
        "Зображення URL": {"url": {}},
        "Аудіо URL": {"url": {}},
        "Відео сценарій": {"rich_text": {}},
        "ID публікацій": {"rich_text": {}},
    })
    created["content_plan"] = db["id"]
    print("   id:", db["id"])
    # Додати зв'язок Кут -> Контент-кути (опційно; якщо 400 — додай в Notion вручну)
    try:
        notion_request(token, "PATCH", "/databases/" + db["id"], {
            "properties": {"Кут": {"relation": {"database_id": created["content_angles"], "single_property": {}}}}
        })
        print("   Кут (relation) додано")
    except Exception as e:
        print("   Кут додай вручну в Notion: Relation na bazu Kontent-kuty. Pomylka:", str(e)[:80])

    # 3. Стратегія / ICP
    print("3. Стратегія / ICP...")
    db = create_database(token, parent_id, "🎯 Стратегія / ICP", {
        "Назва": {"title": {}},
        "Проблема": {"rich_text": {}},
        "ICP": {"rich_text": {}},
        "Цілі 30 днів": {"rich_text": {}},
    })
    created["strategy"] = db["id"]
    print("   id:", db["id"])

    # 4. Бібліотека промптів
    print("4. Бібліотека промптів...")
    db = create_database(token, parent_id, "🔖 Бібліотека промптів", {
        "Назва": {"title": {}},
        "ID промпту": {"rich_text": {}},
        "Текст": {"rich_text": {}},
        "Рейтинг": {"number": {}},
    })
    created["prompts"] = db["id"]
    print("   id:", db["id"])

    # 5. Бібліотека книг
    print("5. Бібліотека книг...")
    db = create_database(token, parent_id, "📚 Бібліотека книг", {
        "Назва": {"title": {}},
        "Автор": {"rich_text": {}},
        "Нотатки": {"rich_text": {}},
    })
    created["books"] = db["id"]
    print("   id:", db["id"])

    # 6. Джерела новин
    print("6. Джерела новин...")
    db = create_database(token, parent_id, "🌐 Джерела новин", {
        "Назва": {"title": {}},
        "RSS URL": {"url": {}},
        "Статус": {"select": {"options": [{"name": "Активний"}, {"name": "Неактивний"}]}},
    })
    created["news_sources"] = db["id"]
    print("   id:", db["id"])

    # 7. Конкуренти
    print("7. Конкуренти...")
    db = create_database(token, parent_id, "🏆 Конкуренти", {
        "Назва": {"title": {}},
        "URL": {"url": {}},
        "Нотатки": {"rich_text": {}},
    })
    created["competitors"] = db["id"]
    print("   id:", db["id"])

    # 8. Статистика
    print("8. Статистика...")
    db = create_database(token, parent_id, "📊 Статистика", {
        "Назва": {"title": {}},
        "Дата": {"date": {}},
        "Метрики": {"rich_text": {}},
    })
    created["stats"] = db["id"]
    print("   id:", db["id"])

    # 9. Медіа-бібліотека
    print("9. Медіа-бібліотека...")
    db = create_database(token, parent_id, "🖼️ Медіа-бібліотека", {
        "Назва": {"title": {}},
        "URL": {"url": {}},
        "Тип": {"select": {"options": [
            {"name": "Зображення"}, {"name": "Аудіо"}, {"name": "Відео"},
        ]}},
    })
    created["media"] = db["id"]
    print("   id:", db["id"])

    # Зберегти ID для n8n та скриптів
    out_path = os.path.join(os.path.dirname(__file__), "..", "NOTION_DATABASE_IDS.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(created, f, indent=2, ensure_ascii=False)
    print("\nГотово. ID збережено в NOTION_DATABASE_IDS.json")
    return created

if __name__ == "__main__":
    main()
