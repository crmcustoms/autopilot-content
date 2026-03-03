# -*- coding: utf-8 -*-
"""
Zapovnyuye Stratehiyu/ICP i Biblioteky knyh STATYCHNO (bez AI).
Vykorystovuye zazdaleghid pydhotovleni dani — dlya pershogo zapusku i testuvannya.
Piznyishe mozhna perezapysaty cherez /strategy (Prompts #1-4).

Zapusk: python scripts/fill_strategy_static.py
"""
import io
import json
import os
import sys
import urllib.request
import urllib.error

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    return len(data.get("results", []))


def rt(text):
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


STRATEGY_TEXT = """HOLOVNA PROBLEMA:

Vlasnyky maloho ta serednoho biznesu v Ukrayini vtrachayut' do 30% potentsiynoho prybutku cherez khaotychne vedennya klientiv: zamovlennya zabuvayut'sya, zaявky vtrachayutsya v mesendzhherakh, menedzhery ne mayut' edynoyi kartky klienta. CRM ye, ale ne nalashtovana pid realni protsesy — i lyudy prosto ne korystuyutsya neyu.

PORTRET TSILOVOYI AUDYTORIYI (ICP):

Khto: vlasnyky kompaniy 5-50 osib, sfera — torhivlya, posluhy, vyrobnytsvo. Vik 32-52, Ukrayina.

Shcho khochut':
- Avtomatyzuvaty rutynni zadachi (zaявky, nahаduvannya, zvity)
- Bачity shcho diiyt'sya z kliyentamy bez potreby pytaty menedzheriv
- Skochuvaty chеs na administer roboti

Shcho stopyт':
- "Ne mayu chasu rozbyraty novyy instrument"
- "My vzhe probuvaly CRM — ne pryzhy losya"
- "Dорого та skladno nalashtovuvaty"

Yak hovoryat':
- "u nas vse v Excel"
- "менеджери самі ведуть свою базу"
- "Bitrix поставили, аленіхто не користується"

Tryhery (koly vyrushayut' kupuvaty):
- Vtratili krupnoho kliyenta cherez zabuvchyvistу
- Novi spivrobitnyky ne znayut' istoriyu klienta
- Vlasnik ne mozhe kontrolyuvaty vidil prodazhiv

Tabu (shcho ne hovoryty):
- "Vam potribno vse pererobyyty z nulya"
- Porivnyuvaty z Bitrix24 abo AmoCRM yak "kraschi"
- Obitsyaty sho vse buде pratsyuvaty z pershogo dnya

TSILI NA 30 DNIV:
- Zrostannya zastosuvannya kanalu: +500 pidpysnykiv
- Lidoghenezys: 10-15 inbound zaявok cherez kontent
- Pidvyshchennya ekspertnoyi doviry: 3 keystudis opublikovano"""


BOOKS = [
    ("Pochynay z Chomu | Start With Why", "Simon Sinek"),
    ("Kliyent na vse zhyttya", "Karl Sewel"),
    ("Vid Nulya do Odnoho | Zero to One", "Peter Thiel"),
    ("Chytach dumok | Never Split the Difference", "Chris Voss"),
    ("Traction", "Gino Wickman"),
    ("The E-Myth Revisited", "Michael E. Gerber"),
    ("Lean Startup", "Eric Ries"),
    ("Spravi ne terplyat' zvolikan' | Eat That Frog", "Brian Tracy"),
    ("7 navychok vysokoefektyvnykh lyudey", "Stephen Covey"),
    ("Myslennya shvydke i povilne | Thinking Fast and Slow", "Daniel Kahneman"),
    ("Vplyv | Influence", "Robert Cialdini"),
    ("Domohovtesia z bud-yam | Getting to Yes", "Roger Fisher"),
    ("Chy my ne pomeremos vid zhydosti | The Hard Thing About Hard Things", "Ben Horowitz"),
    ("Reробота | Rework", "Jason Fried"),
    ("Prodayny pit' | Spin Selling", "Neil Rackham"),
    ("Novyi kodeks lidera | The 21 Irrefutable Laws of Leadership", "John Maxwell"),
    ("Synerhetyka | Good to Great", "Jim Collins"),
    ("Postiyni kilenty | The Loyalty Effect", "Frederick Reichheld"),
    ("Marketynh bez brekhni | This Is Marketing", "Seth Godin"),
    ("Psykholohiya prodazhiv | Psychology of Selling", "Brian Tracy"),
    ("Korporatyvna kultura | The Culture Code", "Daniel Coyle"),
    ("Proryv do velykoho | Built to Last", "Jim Collins"),
    ("Avtopilot | The 4-Hour Workweek", "Tim Ferriss"),
    ("Perekhid | Switch", "Chip Heath"),
    ("Shcho vidriznyaye peremozhtsiv | Outliers", "Malcolm Gladwell"),
    ("Efektyvnyy menedzher | The Effective Executive", "Peter Drucker"),
    ("Tsinnist' dlya kliyenta | Delivering Happiness", "Tony Hsieh"),
    ("Prodavatsia chy ne prodavatsia | To Sell Is Human", "Daniel Pink"),
    ("System Thinker", "Donella Meadows"),
    ("Maysternist perekonannya | Pre-Suasion", "Robert Cialdini"),
    ("Pohlad na biznes | The Personal MBA", "Josh Kaufman"),
    ("Vazhki rozmovy | Difficult Conversations", "Douglas Stone"),
    ("Prodazhny napadaet' | The Challenger Sale", "Matthew Dixon"),
    ("Keystone Habits | The Power of Habit", "Charles Duhigg"),
    ("Bez kompleksiv | Radical Candor", "Kim Scott"),
    ("Metod Bezosa | The Amazon Way", "John Rossman"),
    ("Pivnichna zirka | Measure What Matters", "John Doerr"),
    ("OKR: Tilky holovne | Objectives and Key Results", "Paul Niven"),
    ("Sprint", "Jake Knapp"),
    ("Pryskoryuyte biznes | Blitzscaling", "Reid Hoffman"),
    ("Tsyfrova transformatsiya | The Digital Transformation Playbook", "David Rogers"),
    ("Kreatyvnist' u bizneyi | Creativity Inc", "Ed Catmull"),
    ("Zapuskayte. Mashtabuyuyte. | Scaling Up", "Verne Harnish"),
    ("Klientsky dosvid | The Customer Experience", "Blake Morgan"),
    ("Systema prodazhiv | Predictable Revenue", "Aaron Ross"),
    ("Antykrykhkist' | Antifragile", "Nassim Taleb"),
    ("Chorna lebid' | The Black Swan", "Nassim Taleb"),
    ("Zavtra budem zhyty | Drive", "Daniel Pink"),
    ("Pryntsypy | Principles", "Ray Dalio"),
    ("Filosofiya uspikhu | Meditations", "Marcus Aurelius"),
]


def main():
    env = load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        print("[ERR] NOTION_TOKEN vidsutni v .env")
        sys.exit(1)

    ids = load_db_ids()

    # --- 1. Strategy ---
    print()
    print("=== 1/2: Stratehiya / ICP ===")
    existing = count_records(token, ids["strategy"])
    if existing > 0:
        print(f"  [OK] Vzhe ye zapysy — propuskayemo. (Dlya pereznytky — vydaly vsi zapysy v Notion i zapusky znovu.)")
    else:
        _, err = notion_request(token, "POST", "/pages", {
            "parent": {"database_id": ids["strategy"]},
            "properties": {
                "Назва": {"title": rt("Stratehichna baza — CRMCUSTOMS (pochatkova, statychna)")},
                "Проблема": {"rich_text": rt(STRATEGY_TEXT[:2000])},
                "ICP": {"rich_text": rt(STRATEGY_TEXT[:2000])},
            },
        })
        if err:
            print(f"  [ERR] Notion: {err}")
        else:
            print("  [OK] Stratehiya/ICP zapysana.")
            print("       Ts e STATYCHNYY variant — pislya zapusku /strategy onovysh tsi dani cherez AI.")

    # --- 2. Books ---
    print()
    print("=== 2/2: Biblioteka knyh ===")
    existing = count_records(token, ids["books"])
    if existing > 0:
        print(f"  [OK] Vzhe ye knyhy — propuskayemo.")
    else:
        added = 0
        failed = 0
        for name, author in BOOKS:
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
        print(f"  [OK] Biblioteka knyh: {added} knyh dodano" + (f", {failed} pomylok" if failed else "") + ".")

    print()
    print("Hotovo. Zapusty diagnose.py dlya perevirky.")


if __name__ == "__main__":
    main()
