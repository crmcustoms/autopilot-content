# -*- coding: utf-8 -*-
"""
Проставляє дати записам у Контент-плані, у яких поле «Дата» порожнє.
Бере перші N записів без дати і присвоює їм дні підряд, починаючи з завтра (або з --start YYYY-MM-DD).
Запуск: python scripts/fill_content_plan_dates.py [--start 2026-03-01]
Потрібен .env: NOTION_TOKEN; NOTION_DATABASE_IDS.json.
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

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
    import urllib.request
    import urllib.error

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


def query_pages_without_date(token, database_id, max_pages=50):
    """Повертає список page_id записів, у яких Дата порожня."""
    out = []
    cursor = None
    while len(out) < max_pages:
        body = {
            "filter": {"property": "Дата", "date": {"is_empty": True}},
            "page_size": min(100, max_pages - len(out)),
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
        }
        if cursor:
            body["start_cursor"] = cursor
        data = notion_request(token, "POST", "/databases/" + database_id + "/query", body)
        for r in data.get("results", []):
            out.append(r["id"])
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out[:max_pages]


def main():
    parser = argparse.ArgumentParser(description="Проставити дати в Контент-план")
    parser.add_argument("--start", default=None, help="Початкова дата YYYY-MM-DD (за замовч. завтра)")
    parser.add_argument("--max", type=int, default=31, help="Макс. кількість записів (за замовч. 31)")
    args = parser.parse_args()

    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN у .env відсутній")
        sys.exit(1)
    ids = load_db_ids()
    db_id = ids["content_plan"]

    if args.start:
        try:
            start_date = date.fromisoformat(args.start)
        except ValueError:
            print("Невірний формат --start, потрібно YYYY-MM-DD")
            sys.exit(1)
    else:
        start_date = date.today() + timedelta(days=1)

    page_ids = query_pages_without_date(token, db_id, max_pages=args.max)
    if not page_ids:
        print("Записів без дати в Контент-плані немає.")
        return 0

    updated = 0
    for i, page_id in enumerate(page_ids):
        d = start_date + timedelta(days=i)
        try:
            notion_request(token, "PATCH", "/pages/" + page_id, {
                "properties": {
                    "Дата": {"date": {"start": d.isoformat()}},
                },
            })
            updated += 1
            print("OK:", d.isoformat(), "-> запис", page_id[:18] + "...")
        except Exception as e:
            print("Помилка", page_id[:18], ":", e)
    print("Проставлено дат:", updated)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
