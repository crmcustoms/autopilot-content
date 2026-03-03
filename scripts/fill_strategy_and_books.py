# -*- coding: utf-8 -*-
"""
Zapovnyuye tilky Stratehiyu/ICP i Biblioteky knyh.
Yakshcho Google AI 429 — chekaye 70 sekund i povtoryuye.
Zapusk: python scripts/fill_strategy_and_books.py
"""
import io
import json
import os
import sys
import time
import urllib.request
import urllib.error

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.ai_rotate import get_google_keys_from_env, call_gemini_rotate


def load_env():
    with open(os.path.join(ROOT, ".env"), "r", encoding="utf-8") as f:
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        err = e.read().decode() if e.fp else str(e)
        return None, f"HTTP {e.code}: {err[:300]}"
    except Exception as e:
        return None, str(e)[:200]


def count_records(token, db_id):
    data, err = notion_request(token, "POST", f"/databases/{db_id}/query", {"page_size": 1})
    if err:
        return -1
    # total is not returned directly, so we just check if any exist
    return len(data.get("results", []))


def rt(text):
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def call_ai_with_retry(keys, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return call_gemini_rotate(keys, prompt)
        except RuntimeError as e:
            if "429" in str(e):
                wait = 70
                print(f"  Google AI 429 (limt zapytiv). Chekayu {wait}s... (sproba {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Vycherpano sproby — Google AI ne vidpoviv")


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    keys = get_google_keys_from_env(env)

    if not token:
        print("[ERR] NOTION_TOKEN vidsutni v .env")
        sys.exit(1)
    if not keys:
        print("[ERR] GOOGLE_AI_KEYS vidsutni v .env")
        sys.exit(1)

    ids = load_db_ids()

    # --- 1. Stratehiya/ICP ---
    print()
    print("=== 1/2: Stratehiya / ICP ===")
    existing = count_records(token, ids["strategy"])
    if existing > 0:
        print(f"  [OK] Vzhe ye zapysy ({existing}+) — propuskayemo.")
    else:
        prompt = (
            "Daj odyn korotkyy blok tekstu dlya Notion (ukrayinskoyu):\n"
            "1) Holovna problema nishi CRM dlya maloho biznesu v Ukrayini (2-3 rechennya).\n"
            "2) Tablytsu ICP u vyhlyadi tekstu: khto / shcho khochut / shcho stopyт / "
            "yak hovoryat / tryhery / tabu.\n"
            "Bez zayvoho vstupu."
        )
        print("  Zapyt do Google AI...")
        try:
            text = call_ai_with_retry(keys, prompt)
            _, err = notion_request(token, "POST", "/pages", {
                "parent": {"database_id": ids["strategy"]},
                "properties": {
                    "Назва": {"title": rt("Stratehichna baza (pochatkova)")},
                    "Проблема": {"rich_text": rt(text[:2000])},
                    "ICP": {"rich_text": rt(text[:2000])},
                },
            })
            if err:
                print(f"  [ERR] Notion: {err}")
            else:
                print("  [OK] Stratehiya/ICP — zapysano v Notion.")
        except Exception as e:
            print(f"  [ERR] {e}")

    # --- 2. Biblioteka knyh ---
    print()
    print("=== 2/2: Biblioteka knyh ===")
    existing = count_records(token, ids["books"])
    if existing > 0:
        print(f"  [OK] Vzhe ye knyhy ({existing}+) — propuskayemo.")
    else:
        prompt = (
            "Vyvedit spysok rivno 50 biznes-knyh dlya vlasnykiv maloho biznesu. "
            "Format kozhoho ryadka: Nazva | Avtor\n"
            "Tilky spysok, bez numeratsiyi ta komentariv. Ukrayinskoyu abo anhliyskoyu nazvy."
        )
        print("  Zapyt do Google AI (mozhe zaynyaty do 2 khvylyn)...")
        try:
            text = call_ai_with_retry(keys, prompt)
            lines = [s.strip() for s in text.strip().split("\n") if "|" in s][:50]
            added = 0
            failed = 0
            for line in lines:
                parts = line.split("|", 1)
                name = parts[0].strip()[:2000]
                author = parts[1].strip()[:2000] if len(parts) > 1 else ""
                _, err = notion_request(token, "POST", "/pages", {
                    "parent": {"database_id": ids["books"]},
                    "properties": {
                        "Назва": {"title": rt(name)},
                        "Автор": {"rich_text": rt(author)},
                    },
                })
                if err:
                    failed += 1
                else:
                    added += 1
            print(f"  [OK] Biblioteka knyh — {added} knyh dodano" + (f", {failed} pomylok" if failed else "") + ".")
        except Exception as e:
            print(f"  [ERR] {e}")

    print()
    print("Hotovo. Zapusty diagnose.py dlya perevirky.")


if __name__ == "__main__":
    main()
