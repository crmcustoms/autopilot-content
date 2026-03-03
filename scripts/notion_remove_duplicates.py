# -*- coding: utf-8 -*-
"""
Знаходить дублікати баз на батьківській сторінці Notion і переміщує їх у кошик (in_trash).
Залишає по одній базі на кожну унікальну назву; пріоритет — ID з NOTION_DATABASE_IDS.json.
Запуск: python scripts/notion_remove_duplicates.py
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


def notion_get(token, path):
    url = "https://api.notion.com/v1" + path
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Notion-Version": "2022-06-28"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def notion_patch(token, path, body):
    url = "https://api.notion.com/v1" + path
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_block_children(token, block_id):
    out = []
    cursor = None
    while True:
        path = "/blocks/" + block_id + "/children?page_size=100"
        if cursor:
            path += "&start_cursor=" + cursor
        data = notion_get(token, path)
        for b in data.get("results", []):
            out.append(b)
        if not data.get("next_cursor"):
            break
        cursor = data["next_cursor"]
    return out


def get_db_title(block):
    if block.get("type") != "child_database":
        return None
    title_obj = block.get("child_database", {}).get("title", [])
    if not title_obj:
        return ""
    first = title_obj[0]
    if isinstance(first, dict):
        return first.get("plain_text", "")
    return str(first)


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    parent_id = env.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent_id:
        print("NOTION_TOKEN та NOTION_PARENT_PAGE_ID у .env")
        sys.exit(1)
    keep_ids = set(load_db_ids().values())
    children = get_block_children(token, parent_id)
    by_title = {}
    for b in children:
        if b.get("type") != "child_database":
            continue
        db_id = b.get("id")
        title = get_db_title(b) or "(без назви)"
        title = title.strip()
        if title not in by_title:
            by_title[title] = []
        by_title[title].append(db_id)
    archived = 0
    for title, ids in by_title.items():
        if len(ids) <= 1:
            continue
        to_keep = None
        for i in ids:
            if i in keep_ids:
                to_keep = i
                break
        if to_keep is None:
            to_keep = ids[0]
        for i in ids:
            if i == to_keep:
                continue
            try:
                notion_patch(token, "/pages/" + i, {"in_trash": True})
                print("Архівовано дублікат:", title[:50], "id:", i[:20] + "...")
                archived += 1
            except urllib.error.HTTPError as e:
                print("Помилка архіву", i[:20], e.code)
    if archived == 0:
        print("Дублікатів не знайдено або вже прибрано.")
    else:
        print("У кошик переміщено записів:", archived)


if __name__ == "__main__":
    main()
