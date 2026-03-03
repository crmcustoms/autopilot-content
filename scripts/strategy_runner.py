# -*- coding: utf-8 -*-
"""
Запуск промпту #1 (strategy_base) з Notion -> Claude API -> запис у базу Стратегія/ICP.
Потрібен .env: NOTION_TOKEN, ANTHROPIC_API_KEY; NOTION_DATABASE_IDS.json.
Запуск: python scripts/strategy_runner.py [відповідь на питання промпту]
Якщо без ключа — виводить підказку і виходить.
"""
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.ai_rotate import get_google_keys_from_env, call_gemini_rotate


def load_env():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        raise FileNotFoundError("Немає .env у корені проекту")
    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_db_ids():
    path = os.path.join(ROOT, "NOTION_DATABASE_IDS.json")
    with open(path, "r", encoding="utf-8") as f:
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


def get_prompt_text_from_notion(token, prompts_db_id, prompt_id):
    body = {
        "filter": {"property": "ID промпту", "rich_text": {"contains": prompt_id}}
    }
    out = notion_request(token, "POST", "/databases/" + prompts_db_id + "/query", body)
    results = out.get("results", [])
    if not results:
        return None
    props = results[0].get("properties", {})
    rt = props.get("Текст", {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rt)


def call_claude(api_key, prompt_text, user_reply=""):
    url = "https://api.anthropic.com/v1/messages"
    content = prompt_text
    if user_reply.strip():
        content = prompt_text + "\n\n--- Відповідь користувача ---\n\n" + user_reply
    body = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": content}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def create_notion_page(token, database_id, title, rich_text_props):
    body = {
        "parent": {"database_id": database_id},
        "properties": {
            "Назва": {"title": [{"type": "text", "text": {"content": title[:2000]}}]},
        },
    }
    for key, text in rich_text_props.items():
        if not text:
            continue
        chunks = []
        for i in range(0, len(text), 2000):
            chunks.append({"type": "text", "text": {"content": text[i : i + 2000]}})
        body["properties"][key] = {"rich_text": chunks}
    return notion_request(token, "POST", "/pages", body)


def main():
    env = load_env()
    notion_token = env.get("NOTION_TOKEN")
    google_keys = get_google_keys_from_env(env)
    anthropic_key = env.get("ANTHROPIC_API_KEY") or env.get("CLAUDE_API_KEY")
    if not notion_token:
        print("Додай NOTION_TOKEN у .env")
        sys.exit(1)
    if not google_keys and not anthropic_key:
        print("Додай GOOGLE_AI_KEYS (key1,key2,...) або ANTHROPIC_API_KEY у .env для запуску strategy.")
        sys.exit(0)
    ids = load_db_ids()
    prompt_text = get_prompt_text_from_notion(notion_token, ids["prompts"], "strategy_base")
    if not prompt_text:
        print("Промпт strategy_base не знайдено в Бібліотеці промптів Notion.")
        sys.exit(1)
    user_reply = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    response = ""
    if google_keys:
        print("Виклик Gemini (ротація ключів при 429)...")
        try:
            response = call_gemini_rotate(google_keys, prompt_text, user_reply)
        except Exception as e:
            print("Gemini помилка:", e)
            if anthropic_key:
                print("Пробую Claude...")
                response = call_claude(anthropic_key, prompt_text, user_reply)
            else:
                raise
    if not response and anthropic_key:
        print("Виклик Claude...")
        response = call_claude(anthropic_key, prompt_text, user_reply)
    if not response:
        print("Порожня відповідь Claude.")
        sys.exit(1)
    print("Запис у Notion (Стратегія/ICP)...")
    create_notion_page(
        notion_token,
        ids["strategy"],
        "Стратегічна база (промпт #1)",
        {"Проблема": response[:2000], "ICP": response},
    )
    print("Готово. Перевір базу «Стратегія / ICP» у Notion.")


if __name__ == "__main__":
    main()
