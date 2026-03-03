# -*- coding: utf-8 -*-
"""
Diagnostyka proektu — tilky chytannya, nichogo ne zminyuye.
Zapusk: python scripts/diagnose.py
"""
import io
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# Fiks dlya Windows terminalu (cp1251 -> utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return {}
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


def notion_query(token, database_id, body=None):
    url = "https://api.notion.com/v1/databases/" + database_id + "/query"
    headers = {
        "Authorization": "Bearer " + token,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        err = e.read().decode() if e.fp else str(e)
        return None, f"HTTP {e.code}: {err[:200]}"
    except Exception as e:
        return None, str(e)[:200]


def check_telegram(token):
    url = "https://api.telegram.org/bot" + token + "/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("ok"):
            bot = data["result"]
            return True, f"@{bot.get('username')} ({bot.get('first_name')})"
        return False, str(data)
    except Exception as e:
        return False, str(e)[:150]


def check_notion_connection(token, parent_id):
    pid = parent_id.replace("-", "")
    url = f"https://api.notion.com/v1/blocks/{pid}/children"
    headers = {
        "Authorization": "Bearer " + token,
        "Notion-Version": "2022-06-28",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        count = len(data.get("results", []))
        return True, f"z'yednannya OK — {count} ob'yektiv na batkivskiy storyntsi"
    except urllib.error.HTTPError as e:
        err = e.read().decode() if e.fp else str(e)
        return False, f"HTTP {e.code}: {err[:200]}"
    except Exception as e:
        return False, str(e)[:150]


DB_LABELS = {
    "content_plan":   "Kontent-plan",
    "content_angles": "Kontent-kuty",
    "strategy":       "Stratehiya/ICP",
    "prompts":        "Biblioteka promptiv",
    "books":          "Biblioteka knyh",
    "news_sources":   "Dzherela novyn",
    "competitors":    "Konkurenty",
    "stats":          "Statystyka",
    "media":          "Media-biblioteka",
}

EXPECTED = {
    "content_plan":   (">=7 zapysiv", 7),
    "content_angles": ("7 kutiv", 7),
    "strategy":       (">=1 zapys", 1),
    "prompts":        ("12 promptiv", 12),
    "books":          (">=30 knyh", 30),
    "news_sources":   (">=3 dzherela", 3),
    "competitors":    ("ne obov'yazkovo", 0),
    "stats":          ("ne obov'yazkovo", 0),
    "media":          ("ne obov'yazkovo", 0),
}


def get_all_records(token, db_id):
    all_results = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data, err = notion_query(token, db_id, body)
        if err:
            return None, err
        results = data.get("results", [])
        all_results.extend(results)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return all_results, None


def analyze_content_plan(records):
    with_date = 0
    without_date = 0
    by_status = {}
    for r in records:
        props = r.get("properties", {})
        d = props.get("Data", {}).get("date") or props.get("Дата", {}).get("date")
        if d and d.get("start"):
            with_date += 1
        else:
            without_date += 1
        sel = props.get("Status", {}).get("select") or props.get("Статус", {}).get("select")
        status = sel.get("name", "—") if sel else "—"
        by_status[status] = by_status.get(status, 0) + 1
    return with_date, without_date, by_status


def ok(msg):
    print(f"  [OK]   {msg}")

def warn(msg):
    print(f"  [!!]   {msg}")

def fail(msg):
    print(f"  [ERR]  {msg}")

def sep(n=55):
    print("-" * n)


def main():
    print()
    sep()
    print("  DIAGNOSTYKA — Autopilot Content")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    sep()

    # --- Env ---
    env = load_env()
    if not env:
        fail(".env ne znaydeno v koreni proektu!")
        return

    print()
    print("1. ZMINNI (.env)")
    sep()

    notion_token = env.get("NOTION_TOKEN", "")
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    parent_id = env.get("NOTION_PARENT_PAGE_ID", "")
    google_keys = env.get("GOOGLE_AI_KEYS", "") or env.get("GOOGLE_AI_KEY_1", "")
    anthropic_key = env.get("ANTHROPIC_API_KEY", "") or env.get("CLAUDE_API_KEY", "")

    env_checks = [
        ("NOTION_TOKEN", notion_token, True),
        ("NOTION_PARENT_PAGE_ID", parent_id, False),
        ("TELEGRAM_BOT_TOKEN", tg_token, True),
        ("GOOGLE_AI_KEYS / KEY_1", google_keys, False),
        ("ANTHROPIC_API_KEY", anthropic_key, False),
    ]
    critical_ok = True
    for name, val, critical in env_checks:
        if val:
            ok(f"{name}: zadano (***{val[-4:]})")
        elif critical:
            fail(f"{name}: VIDSUTNO — bez tsogo ne pratsyuye!")
            critical_ok = False
        else:
            warn(f"{name}: ne zadano (ne obov'yazkovo zaraz)")

    if not critical_ok:
        print()
        fail("Krytychni tokeny vidsutni. Perevirte .env i zapustit znovu.")
        return

    if not google_keys and not anthropic_key:
        warn("Nemaye ni Google AI, ni Anthropic klyuchiv — /strategy ne pratsyuvatyme")

    # --- Telegram ---
    print()
    print("2. TELEGRAM BOT")
    sep()
    tg_ok, tg_msg = check_telegram(tg_token)
    if tg_ok:
        ok(tg_msg)
    else:
        fail(f"Bot ne vidpovidaye: {tg_msg}")

    # --- Notion connection ---
    print()
    print("3. NOTION Z'YEDNANNYA")
    sep()
    if parent_id:
        conn_ok, conn_msg = check_notion_connection(notion_token, parent_id)
        if conn_ok:
            ok(conn_msg)
        else:
            fail(conn_msg)
    else:
        warn("NOTION_PARENT_PAGE_ID ne zadano — propuskayemo")

    # --- DB IDs file ---
    print()
    print("4. NOTION BAZY DANYKH")
    sep()
    try:
        ids = load_db_ids()
    except Exception as e:
        fail(f"NOTION_DATABASE_IDS.json: {e}")
        return

    problems = []
    content_plan_records = None

    for key, label in DB_LABELS.items():
        db_id = ids.get(key)
        if not db_id:
            fail(f"{label}: ID vidsutni v NOTION_DATABASE_IDS.json")
            problems.append(f"Nemaye ID dlya {key}")
            continue

        records, err = get_all_records(notion_token, db_id)
        if err:
            fail(f"{label}: pomylka dostupu — {err}")
            problems.append(f"{label}: pomylka dostupu")
            continue

        count = len(records)
        exp_label, exp_min = EXPECTED[key]

        if exp_min == 0:
            ok(f"{label}: {count} zapysiv")
        elif count >= exp_min:
            ok(f"{label}: {count} zapysiv (ochikuvalosya {exp_label})")
        elif count > 0:
            warn(f"{label}: lyshe {count} zapysiv (ochikuvalosya {exp_label})")
            problems.append(f"{label}: malo zapysiv ({count}/{exp_min})")
        else:
            fail(f"{label}: POROZHNYO (ochikuvalosya {exp_label})")
            problems.append(f"{label}: porozhnyo")

        if key == "content_plan" and records:
            content_plan_records = records

    # --- Content plan detail ---
    if content_plan_records is not None:
        print()
        print("5. KONTENT-PLAN — DETALI")
        sep()
        with_date, without_date, by_status = analyze_content_plan(content_plan_records)
        print(f"  Vsyogo zapysiv:        {len(content_plan_records)}")
        print(f"  Z datoyu (v hrafiku):  {with_date}")
        print(f"  Bez daty:              {without_date}")
        print(f"  Statusy:")
        for st, cnt in sorted(by_status.items(), key=lambda x: -x[1]):
            print(f"    - {st}: {cnt}")

        if with_date == 0:
            warn("ZHOДЕН zapys ne maye daty — /plan i /today povernut porozhni rezult!")
            problems.append("Kontent-plan: 0 zapysiv z datoyu — zapusty fill_content_plan_dates.py")
        else:
            ok(f"{with_date} zapysiv z datoyu — /plan i /today mayut pratsyuvaty")

        if without_date > 0:
            warn(f"{without_date} zapysiv bez daty — zapusty fill_content_plan_dates.py")

    elif content_plan_records is None:
        pass  # pomylka vzhe vivedena vyshche

    # --- Summary ---
    print()
    sep()
    print("  PIDSUMOK")
    sep()
    if not problems:
        ok("Vse vyhlyadaye dobre. Hotovo do testuvannya bota.")
        print()
        print("  NASTUPNI KROKY:")
        print("  1. Zapusty bota:  python -m bot.bot")
        print("  2. Pishyt v bot /today")
        print("  3. Pishyt v bot /plan")
    else:
        print(f"  Znayshlo {len(problems)} problem(y):")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        print()
        print("  NASTUPNI KROKY (po cherzi):")
        step = 1
        if any("porozhnyo" in p or "malo" in p for p in problems if "Biblioteka" in p or "knyh" in p.lower()):
            print(f"  {step}. python scripts/seed_bases_initial.py")
            step += 1
        if any("promptiv" in p for p in problems):
            print(f"  {step}. python scripts/fill_prompts_notion.py")
            step += 1
        if any("kutiv" in p or "angles" in p.lower() for p in problems):
            print(f"  {step}. python scripts/import_initial_angles.py")
            step += 1
        if any("daty" in p for p in problems):
            print(f"  {step}. python scripts/fill_content_plan_dates.py")
            step += 1
        if any("dostup" in p for p in problems):
            print(f"  {step}. Perevirte NOTION_TOKEN u .env")
            step += 1
    print()


if __name__ == "__main__":
    main()
