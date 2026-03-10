# -*- coding: utf-8 -*-
"""
Telegram-бот @crmcontent_bot
Два паралельні флоу затвердження:
  1. TG-пости (content_plan, статус «На затвердженні»)
     pub:/rev:/rej: → публікація в TG канал
  2. Статті блогу (Blog DB, статус «Готово до публікації»)
     bpub:/brej: → Notion Blog (Завершено + Публиковать=True) + авто TG анонс → канал
  3. Фото від адміна → "Завантажити в сховище" → S3 URL

Запуск: python -m bot.bot  (з кореня проекту)
"""
import io, json, os, sys, threading, time, urllib.request, urllib.error, uuid
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─── CONFIG ─────────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    else:
        # Docker/Coolify — читаємо зі змінних середовища
        env = dict(os.environ)
    return env

def load_db_ids():
    with open(os.path.join(ROOT, "NOTION_DATABASE_IDS.json"), encoding="utf-8") as f:
        return json.load(f)

# ─── NOTION ─────────────────────────────────────────────────────────────────

def notion_req(token, method, path, body=None):
    url = "https://api.notion.com/v1" + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer " + token,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, str(e)[:200]

def notion_query(token, db_id, filter_body=None):
    body = {"page_size": 50}
    if filter_body:
        body["filter"] = filter_body
    data, err = notion_req(token, "POST", f"/databases/{db_id}/query", body)
    return (data.get("results", []) if data else []), err

def get_plain(prop, key="title"):
    return "".join(t.get("plain_text", "") for t in prop.get(key, []) if isinstance(t, dict))

def rt(text):
    chunks = []
    for i in range(0, len(str(text)), 2000):
        chunks.append({"type": "text", "text": {"content": str(text)[i:i+2000]}})
    return chunks

# ─── TG POST PARSER (content_plan) ──────────────────────────────────────────

def parse_post(page):
    p = page.get("properties", {})
    return {
        "id":        page["id"],
        "name":      get_plain(p.get("Назва", {}), "title"),
        "status":    (p.get("Статус", {}).get("select") or {}).get("name", ""),
        "text":      get_plain(p.get("Текст посту", {}), "rich_text"),
        "type":      (p.get("Тип", {}).get("select") or {}).get("name", "Піст"),
        "platforms": [m.get("name", "") for m in p.get("Платформи", {}).get("multi_select", [])],
    }

# ─── BLOG ARTICLE PARSER (Blog DB) ──────────────────────────────────────────

def parse_blog(page):
    """Парсить сторінку Notion Blog DB."""
    p = page.get("properties", {})
    def rtp(fname):
        return get_plain(p.get(fname, {}), "rich_text")
    # Title: \ufeffName (title type)
    name_prop = p.get("\ufeffName", {})
    title = get_plain(name_prop, "title") or rtp("H1")
    notion_url = page.get("url", "")
    return {
        "id":          page["id"],
        "title":       title,
        "h1":          rtp("H1"),
        "description": rtp("description"),
        "slug":        rtp("linkName"),
        "photo":       rtp("photo1"),
        "notion_url":  notion_url,
    }

# ─── TELEGRAM ───────────────────────────────────────────────────────────────

def tg_req(token, method, body=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:150]

def send(token, chat_id, text, keyboard=None, parse_mode="Markdown"):
    body = {"chat_id": chat_id, "text": text[:4000]}
    if keyboard:
        body["reply_markup"] = keyboard
    if parse_mode:
        body["parse_mode"] = parse_mode
    return tg_req(token, "sendMessage", body)

def edit_msg(token, chat_id, msg_id, text, keyboard=None):
    body = {"chat_id": chat_id, "message_id": msg_id, "text": text[:4000]}
    if keyboard:
        body["reply_markup"] = keyboard
    body["parse_mode"] = "Markdown"
    return tg_req(token, "editMessageText", body)

def answer_cb(token, cb_id, text=""):
    return tg_req(token, "answerCallbackQuery", {"callback_query_id": cb_id, "text": text})

def publish_to_channel(token, channel_id, text):
    body = {"chat_id": channel_id, "text": text[:4096], "parse_mode": "Markdown"}
    return tg_req(token, "sendMessage", body)

# ─── CLAUDE ─────────────────────────────────────────────────────────────────

def call_claude(api_key, prompt, max_tokens=600):
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["content"][0]["text"]

def generate_blog_tg_announce(api_key, article):
    """Генерує TG анонс для щойно опублікованої статті блогу."""
    site_url = f'https://crmcustoms.com/uk/blog/{article["slug"]}/' if article["slug"] else "https://crmcustoms.com/uk/blog/"
    prompt = (
        f"Напиши анонс (50-70 слів) для Telegram каналу @prodayslonakume.\n\n"
        f"Стаття: {article['title']}\n"
        f"Опис: {article['description']}\n"
        f"Посилання: {site_url}\n\n"
        f"Формат: emoji + *жирний заголовок*, два речення про суть, потім посилання.\n"
        f"Мова: українська. Лише текст поста."
    )
    try:
        return call_claude(api_key, prompt, max_tokens=300)
    except Exception as e:
        # Fallback без Claude
        return (
            f"📝 *{article['title']}*\n\n"
            f"{article['description']}\n\n"
            f"Читати: {site_url}"
        )

# ─── S3 ─────────────────────────────────────────────────────────────────────

def s3_upload(env, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
    """Завантажує bytes у S3-сумісне сховище, повертає публічний URL."""
    import boto3
    from botocore.client import Config

    endpoint  = env.get("S3_ENDPOINT", "").rstrip("/")
    access    = env.get("S3_ACCESS_KEY", "")
    secret    = env.get("S3_SECRET_KEY", "")
    bucket    = env.get("S3_BUCKET", "")
    region    = env.get("S3_REGION", "us-east-1")
    pub_url   = env.get("S3_PUBLIC_URL", "").rstrip("/")

    kwargs = dict(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region,
        # path-style обов'язковий для bucket-names з крапками (напр. crmcustoms.site)
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    if endpoint:
        kwargs["endpoint_url"] = endpoint

    s3 = boto3.client("s3", **kwargs)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )

    if pub_url:
        return f"{pub_url}/{key}"
    elif endpoint:
        return f"{endpoint}/{bucket}/{key}"
    else:
        # path-style URL — без крапок у піддомені, SSL працює коректно
        return f"https://s3.{region}.amazonaws.com/{bucket}/{key}"


def tg_download_file(token: str, file_id: str) -> bytes:
    """Завантажує файл з Telegram серверів, повертає bytes."""
    resp, err = tg_req(token, "getFile", {"file_id": file_id})
    if err or not resp:
        raise RuntimeError(f"getFile error: {err}")
    file_path = resp.get("result", {}).get("file_path", "")
    if not file_path:
        raise RuntimeError("file_path is empty")
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


# ─── STATE ──────────────────────────────────────────────────────────────────
# chat_id -> {"page_id", "original_text", "msg_id", "name"}
_waiting_revision = {}
# page_id -> не надсилати двічі (для обох флоу)
_sent_for_review      = set()   # content_plan posts
_blog_sent_for_review = set()   # blog articles
# chat_id -> {"file_id": ..., "msg_id": ...}  (фото чекає дії)
_pending_photo = {}
_lock = threading.Lock()

# ─── KEYBOARDS ──────────────────────────────────────────────────────────────

def post_keyboard(page_id):
    """Клавіатура для TG-поста."""
    return {"inline_keyboard": [[
        {"text": "✅ Опублікувати в TG", "callback_data": f"pub:{page_id}"},
        {"text": "✏️ Доробити",          "callback_data": f"rev:{page_id}"},
        {"text": "❌ Відхилити",          "callback_data": f"rej:{page_id}"},
    ]]}

def blog_keyboard(page_id):
    """Клавіатура для статті блогу."""
    return {"inline_keyboard": [[
        {"text": "✅ Публікувати на сайт + TG", "callback_data": f"bpub:{page_id}"},
        {"text": "✏️ Доробити",                 "callback_data": f"brev:{page_id}"},
        {"text": "❌ Залишити як є",             "callback_data": f"brej:{page_id}"},
    ]]}

# ─── CHECK CONTENT_PLAN POSTS ───────────────────────────────────────────────

def check_and_send_posts(token, notion_token, db_ids, admin_chat_id):
    """Шукає TG-пости зі статусом «На затвердженні» і надсилає на схвалення."""
    pages, err = notion_query(
        notion_token, db_ids["content_plan"],
        filter_body={"property": "Статус", "select": {"equals": "На затвердженні"}}
    )
    if err:
        print(f"[posts] Notion error: {err}")
        return 0

    count = 0
    for page in pages:
        # Максимум 1 пост за раз
        if count >= 1:
            break
        post = parse_post(page)

        # Пропускаємо пости без тексту — нема чого затверджувати
        if not (post["text"] or "").strip():
            print(f"[posts] Skip empty post: {post['name'][:50]}")
            continue

        with _lock:
            if post["id"] in _sent_for_review:
                continue
            _sent_for_review.add(post["id"])

        platforms = ", ".join(post["platforms"]) if post["platforms"] else "Telegram"
        msg = f"*📣 TG Пост* | {post['type']} | {platforms}\n\n{post['text']}"
        result, err = send(token, admin_chat_id, msg, keyboard=post_keyboard(post["id"]))
        if err:
            print(f"[posts] send error: {err}")
            with _lock:
                _sent_for_review.discard(post["id"])
        else:
            # Статус «На розгляді» — при рестарті бот не пришле знову
            notion_req(notion_token, "PATCH", f"/pages/{post['id']}",
                {"properties": {"Статус": {"select": {"name": "На розгляді"}}}})
            count += 1

    if count:
        print(f"[posts] Sent {count} posts for review")
    return count

# ─── CHECK BLOG ARTICLES ────────────────────────────────────────────────────

def check_and_send_blog_articles(token, blog_token, blog_db, admin_chat_id):
    """Шукає статті зі статусом «Готово до публікації» де дата публікації <= сьогодні."""
    if not blog_token or not blog_db:
        return 0

    from datetime import date as _date
    today = str(_date.today())

    # Шукаємо статті готові до публікації з датою <= сьогодні
    pages, err = notion_query(
        blog_token, blog_db,
        filter_body={"and": [
            {"property": "Status", "multi_select": {"contains": "Готово до публікації"}},
            {"property": "Дата публікації", "date": {"on_or_before": today}},
        ]}
    )
    if err:
        print(f"[blog] Notion error: {err}")
        return 0

    count = 0
    for page in pages:
        # Максимум 1 стаття за раз — щоб не спамити
        if count >= 1:
            break
        article = parse_blog(page)

        slug = article["slug"] or ""
        site_url = f"https://crmcustoms.com/uk/blog/{slug}/" if slug else "(slug не заповнено)"
        desc = article["description"] or "_опис відсутній_"

        msg = (
            f"*📄 Нова стаття для сайту*\n\n"
            f"*Заголовок:* {article['title'] or '?'}\n"
            f"*URL:* `{site_url}`\n\n"
            f"*Опис:* {desc[:300]}\n\n"
            f"[Переглянути в Notion]({article['notion_url']})\n\n"
            f"Після схвалення → сайт + TG анонс у канал."
        )
        result, err = send(token, admin_chat_id, msg, keyboard=blog_keyboard(article["id"]))
        if err:
            print(f"[blog] send error: {err}")
        else:
            # Змінюємо статус на «На розгляді» — при рестарті бот не пришле знову
            notion_req(blog_token, "PATCH", f"/pages/{article['id']}",
                {"properties": {"Status": {"multi_select": [{"name": "На розгляді"}]}}})
            count += 1

    if count:
        print(f"[blog] Sent {count} articles for review")
    return count

# ─── SCHEDULER ──────────────────────────────────────────────────────────────

def scheduler_loop(token, notion_token, db_ids, blog_token, blog_db, admin_chat_id, interval=300):
    print(f"[scheduler] Started. Check every {interval}s | posts + blog articles")
    while True:
        try:
            check_and_send_posts(token, notion_token, db_ids, admin_chat_id)
            check_and_send_blog_articles(token, blog_token, blog_db, admin_chat_id)
        except Exception as e:
            print(f"[scheduler] Error: {e}")
        time.sleep(interval)

# ─── CALLBACK HANDLER ───────────────────────────────────────────────────────

def handle_callback(token, notion_token, db_ids, blog_token, blog_db,
                    channel_id, admin_chat_id, env, update):
    cb      = update["callback_query"]
    cb_id   = cb["id"]
    data    = cb.get("data", "")
    msg     = cb.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    msg_id  = msg.get("message_id")
    answer_cb(token, cb_id)

    api_key = env.get("ANTHROPIC_API_KEY", "")

    # ════════════ TG POST FLOW ════════════

    if data.startswith("pub:"):
        page_id = data[4:]
        page_data, err = notion_req(notion_token, "GET", f"/pages/{page_id}")
        if err:
            edit_msg(token, chat_id, msg_id, f"Помилка Notion: {err}"); return
        post = parse_post(page_data)
        content = post["text"] or post["name"]
        if not content.strip():
            edit_msg(token, chat_id, msg_id, "Текст порожній. Заповни у Notion."); return

        result, err = publish_to_channel(token, channel_id, content)
        if err:
            edit_msg(token, chat_id, msg_id, f"Помилка TG: {err}"); return

        notion_req(notion_token, "PATCH", f"/pages/{page_id}",
            {"properties": {"Статус": {"select": {"name": "Опубліковано"}}}})
        msg_num = result.get("result", {}).get("message_id", "?")
        edit_msg(token, chat_id, msg_id,
            f"✅ Опубліковано в {channel_id} (#{msg_num})\n\n{content[:400]}")
        with _lock:
            _sent_for_review.discard(page_id)
        print(f"[pub] TG post: {post['name'][:50]}")

    elif data.startswith("rev:"):
        page_id = data[4:]
        page_data, err = notion_req(notion_token, "GET", f"/pages/{page_id}")
        if err:
            edit_msg(token, chat_id, msg_id, f"Помилка Notion: {err}"); return
        post = parse_post(page_data)
        with _lock:
            _waiting_revision[str(chat_id)] = {
                "page_id": page_id, "original_text": post["text"],
                "msg_id": msg_id, "name": post["name"], "type": "post",
            }
        edit_msg(token, chat_id, msg_id,
            f"*Доробка поста:*\n_{post['name'][:80]}_\n\n"
            f"Напиши що змінити — і я перепишу через Claude.\n"
            f"Приклади:\n"
            f"• «зроби коротше»\n"
            f"• «додай кейс з цифрами»\n"
            f"• «змін тон на більш розмовний»\n\n"
            f"_/cancel щоб скасувати_")

    elif data.startswith("rej:"):
        page_id = data[4:]
        notion_req(notion_token, "PATCH", f"/pages/{page_id}",
            {"properties": {"Статус": {"select": {"name": "Ідея"}}}})
        edit_msg(token, chat_id, msg_id, "❌ Відхилено → статус «Ідея» в Notion.")
        with _lock:
            _sent_for_review.discard(page_id)

    elif data.startswith("rev_ok:"):
        page_id = data[7:]
        page_data, _ = notion_req(notion_token, "GET", f"/pages/{page_id}")
        if page_data:
            post = parse_post(page_data)
            content = post["text"] or post["name"]
            result, err = publish_to_channel(token, channel_id, content)
            if err:
                send(token, chat_id, f"Помилка: {err}"); return
            notion_req(notion_token, "PATCH", f"/pages/{page_id}",
                {"properties": {"Статус": {"select": {"name": "Опубліковано"}}}})
            msg_num = result.get("result", {}).get("message_id", "?")
            send(token, chat_id, f"✅ Опубліковано #{msg_num}")
            with _lock:
                _sent_for_review.discard(page_id)

    elif data.startswith("rev_again:"):
        page_id = data[10:]
        page_data, _ = notion_req(notion_token, "GET", f"/pages/{page_id}")
        if page_data:
            post = parse_post(page_data)
            with _lock:
                _waiting_revision[str(chat_id)] = {
                    "page_id": page_id, "original_text": post["text"],
                    "msg_id": msg_id, "name": post["name"], "type": "post",
                }
            send(token, chat_id, "Напиши нові побажання:")

    # ════════════ BLOG ARTICLE FLOW ════════════

    elif data.startswith("bpub:"):
        page_id = data[5:]
        page_data, err = notion_req(blog_token, "GET", f"/pages/{page_id}")
        if err:
            edit_msg(token, chat_id, msg_id, f"Помилка Blog Notion: {err}"); return

        article = parse_blog(page_data)
        send(token, chat_id, "⏳ Публікую статтю...")

        # 1. Оновити Notion Blog: Завершено + Публиковать=True
        update_body = {
            "properties": {
                "Status":      {"multi_select": [{"name": "Завершено"}]},
                "Публиковать": {"checkbox": True},
            }
        }
        _, err = notion_req(blog_token, "PATCH", f"/pages/{page_id}", update_body)
        if err:
            send(token, chat_id, f"Помилка оновлення Notion: {err}"); return

        # 2. Генерувати TG анонс і опублікувати в канал
        tg_text = generate_blog_tg_announce(api_key, article)
        result, tg_err = publish_to_channel(token, channel_id, tg_text)
        msg_num = result.get("result", {}).get("message_id", "?") if result else "?"

        slug = article["slug"] or ""
        site_url = f"https://crmcustoms.com/uk/blog/{slug}/" if slug else "crmcustoms.com/uk/blog/"

        if tg_err:
            status_text = f"⚠️ TG помилка: {tg_err}"
        else:
            status_text = f"✅ TG анонс опубліковано (#{msg_num})"

        edit_msg(token, chat_id, msg_id,
            f"*✅ Статтю опубліковано!*\n\n"
            f"*Сайт:* {site_url}\n"
            f"{status_text}\n\n"
            f"*TG анонс:*\n{tg_text[:300]}")

        with _lock:
            _blog_sent_for_review.discard(page_id)
        print(f"[bpub] Blog article published: {article['title'][:50]}")

    elif data.startswith("brej:"):
        page_id = data[5:]
        from datetime import date as _date, timedelta as _td
        tomorrow = str(_date.today() + _td(days=1))
        # Повертаємо «Готово до публікації» + переносимо дату на завтра
        # (щоб бот не прислав знову через 5 хв у той же день)
        notion_req(blog_token, "PATCH", f"/pages/{page_id}", {
            "properties": {
                "Status": {"multi_select": [{"name": "Готово до публікації"}]},
                "Дата публікації": {"date": {"start": tomorrow}},
            }
        })
        edit_msg(token, chat_id, msg_id,
            "⏸ Залишено. Стаття повернеться на схвалення завтра.")
        with _lock:
            _blog_sent_for_review.discard(page_id)

    elif data.startswith("brev:"):
        page_id = data[5:]
        page_data, err = notion_req(blog_token, "GET", f"/pages/{page_id}")
        if err:
            edit_msg(token, chat_id, msg_id, f"Помилка Notion: {err}"); return
        article = parse_blog(page_data)
        with _lock:
            _waiting_revision[str(chat_id)] = {
                "page_id": page_id, "original_text": article["title"],
                "msg_id": msg_id, "name": article["title"], "type": "blog",
            }
        edit_msg(token, chat_id, msg_id,
            f"*Доробка статті:*\n_{article['title'][:80]}_\n\n"
            f"Напиши що виправити — Claude перепише і поверне на схвалення.\n"
            f"Приклади:\n"
            f"• «зроби вступ коротший»\n"
            f"• «додай практичний приклад у третій розділ»\n"
            f"• «заголовок більш конкретний»\n\n"
            f"_/cancel щоб скасувати_")

    # ════════════ PHOTO UPLOAD FLOW ════════════

    elif data == "imgup":
        with _lock:
            photo_state = _pending_photo.pop(str(chat_id), None)
        if not photo_state:
            edit_msg(token, chat_id, msg_id, "⚠️ Фото не знайдено. Надішли ще раз."); return

        edit_msg(token, chat_id, msg_id, "⏳ Завантажую в сховище...")

        try:
            img_bytes = tg_download_file(token, photo_state["file_id"])
        except Exception as e:
            edit_msg(token, chat_id, msg_id, f"❌ Помилка завантаження з TG: {e}"); return

        # Генеруємо унікальне ім'я файлу
        ts  = datetime.now().strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:6]
        key = f"uploads/{ts}-{uid}.jpg"

        try:
            url = s3_upload(env, img_bytes, key, "image/jpeg")
        except Exception as e:
            edit_msg(token, chat_id, msg_id, f"❌ Помилка S3: {e}"); return

        edit_msg(token, chat_id, msg_id,
            f"✅ *Завантажено в сховище!*\n\n"
            f"`{url}`\n\n"
            f"_Скопіюй посилання та встав у статтю._")
        print(f"[imgup] Uploaded: {url}")

    elif data == "imgcancel":
        with _lock:
            _pending_photo.pop(str(chat_id), None)
        edit_msg(token, chat_id, msg_id, "Скасовано.")

# ─── MESSAGE HANDLER ────────────────────────────────────────────────────────

def handle_message(token, notion_token, db_ids, channel_id, admin_chat_id, env, msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    # ─── Обробка фото (до перевірки тексту!) ─────────────────────────────────
    photos = msg.get("photo")
    if photos:
        file_id = photos[-1]["file_id"]   # найбільший розмір
        msg_id  = msg.get("message_id")
        with _lock:
            _pending_photo[str(chat_id)] = {"file_id": file_id, "msg_id": msg_id}
        keyboard = {"inline_keyboard": [[
            {"text": "📤 Завантажити в сховище", "callback_data": "imgup"},
            {"text": "❌ Скасувати",              "callback_data": "imgcancel"},
        ]]}
        send(token, chat_id, "Що зробити з цим фото?", keyboard=keyboard)
        return

    if not text:
        return

    with _lock:
        revision_state = _waiting_revision.get(str(chat_id))

    if revision_state and not text.startswith("/"):
        _handle_revision_request(token, notion_token, env, chat_id, text, revision_state)
        return

    if text == "/start":
        send(token, chat_id,
            "*CRM Content Bot*\n\n"
            "*TG пости (content_plan):*\n"
            "✅ Опублікувати → в канал\n"
            "✏️ Доробити → Claude переписує\n"
            "❌ Відхилити → статус «Ідея»\n\n"
            "*Статті блогу (Blog DB):*\n"
            "✅ Публікувати → сайт + авто TG анонс\n"
            "✏️ Доробити → Claude виправляє, повертає на схвалення\n"
            "❌ Залишити як є → статус не змінюється\n\n"
            "Команди: /check /plan /today /checkblog")
        return

    if text == "/cancel":
        with _lock:
            _waiting_revision.pop(str(chat_id), None)
        send(token, chat_id, "Скасовано.")
        return

    if text == "/check":
        send(token, chat_id, "Перевіряю TG пости...")
        blog_token = env.get("NOTION_BLOG_TOKEN", "")
        blog_db    = env.get("NOTION_BLOG_DB_ID", "")
        check_and_send_posts(token, notion_token, db_ids, admin_chat_id)
        check_and_send_blog_articles(token, blog_token, blog_db, admin_chat_id)
        return

    if text == "/checkblog":
        blog_token = env.get("NOTION_BLOG_TOKEN", "")
        blog_db    = env.get("NOTION_BLOG_DB_ID", "")
        send(token, chat_id, "Перевіряю Blog DB...")
        check_and_send_blog_articles(token, blog_token, blog_db, admin_chat_id)
        return

    if text == "/plan":
        _cmd_plan(token, notion_token, db_ids, chat_id)
        return

    if text == "/today":
        _cmd_today(token, notion_token, db_ids, chat_id)
        return

    if len(text) >= 20:
        _save_draft(token, notion_token, db_ids, chat_id, text)
        return

    send(token, chat_id,
        "Команди: /check /checkblog /plan /today\n"
        "Або надішли текст поста — збережу як чернетку.")


def _handle_revision_request(token, notion_token, env, chat_id, wishes, state):
    """Переписує TG-пост або статтю блогу через Claude."""
    api_key   = env.get("ANTHROPIC_API_KEY", "")
    blog_token = env.get("NOTION_BLOG_TOKEN", "")
    if not api_key:
        send(token, chat_id, "ANTHROPIC_API_KEY не задано."); return

    page_id   = state["page_id"]
    original  = state["original_text"]
    name      = state["name"]
    item_type = state.get("type", "post")

    with _lock:
        _waiting_revision.pop(str(chat_id), None)

    send(token, chat_id, "✍️ Переписую через Claude...")

    if item_type == "blog":
        # Для статті — отримуємо повний текст зі сторінки Notion, передаємо побажання
        page_data, err = notion_req(blog_token, "GET", f"/pages/{page_id}")
        if err:
            send(token, chat_id, f"Помилка Notion: {err}"); return
        article = parse_blog(page_data)
        prompt = (
            f"Ти — контент-менеджер CRMCUSTOMS. Доопрацюй статтю згідно побажань.\n\n"
            f"СТАТТЯ: {article['title']}\n"
            f"ОПИС: {article['description']}\n\n"
            f"ПОБАЖАННЯ: {wishes}\n\n"
            f"Поверни JSON з полями які треба оновити:\n"
            f"{{\"title\": \"...\", \"description\": \"...\"}}\n"
            f"Якщо поле не змінюється — залиш як є. ТІЛЬКИ JSON, без пояснень."
        )
        try:
            raw = call_claude(api_key, prompt, max_tokens=500)
            import re as _re
            m = _re.search(r'\{.*\}', raw, _re.DOTALL)
            updates = json.loads(m.group()) if m else {}
        except Exception:
            updates = {}

        patch_props = {}
        if updates.get("title"):
            patch_props["\ufeffName"] = {"title": rt(updates["title"][:100])}
            patch_props["H1"]        = {"rich_text": rt(updates["title"][:2000])}
        if updates.get("description"):
            patch_props["description"] = {"rich_text": rt(updates["description"][:300])}
        if patch_props:
            notion_req(blog_token, "PATCH", f"/pages/{page_id}", {"properties": patch_props})

        keyboard = {"inline_keyboard": [[
            {"text": "✅ Публікувати на сайт + TG", "callback_data": f"bpub:{page_id}"},
            {"text": "✏️ Доробити ще",              "callback_data": f"brev:{page_id}"},
            {"text": "❌ Залишити як є",             "callback_data": f"brej:{page_id}"},
        ]]}
        preview = f"*{updates.get('title', article['title'])}*\n_{updates.get('description', article['description'])}_"
        send(token, chat_id, f"*Дороблено:*\n\n{preview}\n\nОновлено в Notion.", keyboard=keyboard)
        with _lock:
            _blog_sent_for_review.discard(page_id)
        print(f"[brev] Blog revised: {name[:40]}")

    else:
        # TG пост — стара логіка
        prompt = (
            f"Ти — Максим з CRMCUSTOMS. Перепиши пост згідно побажань.\n\n"
            f"ОРИГІНАЛ:\n{original}\n\n"
            f"ПОБАЖАННЯ:\n{wishes}\n\n"
            f"Правила: тільки українська, 150-220 слів, Telegram Markdown (*жирний*), "
            f"emoji на початку заголовку. Виведи ТІЛЬКИ текст поста."
        )
        try:
            new_text = call_claude(api_key, prompt)
        except Exception as e:
            send(token, chat_id, f"Помилка Claude: {e}"); return

        notion_req(notion_token, "PATCH", f"/pages/{page_id}",
            {"properties": {"Текст посту": {"rich_text": rt(new_text)}}})

        keyboard = {"inline_keyboard": [[
            {"text": "✅ Опублікувати в TG",  "callback_data": f"rev_ok:{page_id}"},
            {"text": "✏️ Доробити ще",        "callback_data": f"rev_again:{page_id}"},
            {"text": "❌ Відхилити",           "callback_data": f"rej:{page_id}"},
        ]]}
        send(token, chat_id, f"*Дороблено:*\n\n{new_text}", keyboard=keyboard)
        print(f"[rev] Revised: {name[:40]}")


def _save_draft(token, notion_token, db_ids, chat_id, text):
    title = text[:80].split("\n")[0]
    _, err = notion_req(notion_token, "POST", "/pages", {
        "parent": {"database_id": db_ids["content_plan"]},
        "properties": {
            "Назва":       {"title": rt(title)},
            "Текст посту": {"rich_text": rt(text)},
            "Статус":      {"select": {"name": "Ідея"}},
            "Платформи":   {"multi_select": [{"name": "Telegram"}]},
        },
    })
    if err:
        send(token, chat_id, f"Помилка збереження: {err}")
    else:
        send(token, chat_id,
            "💾 Збережено як «Ідея» в Notion.\n"
            "Постав статус «На затвердженні» → пришлю на схвалення.")


def _cmd_plan(token, notion_token, db_ids, chat_id):
    date_from = datetime.now().strftime("%Y-%m-%d")
    date_to = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    pages, err = notion_query(notion_token, db_ids["content_plan"], filter_body={"and": [
        {"property": "Дата", "date": {"on_or_after": date_from}},
        {"property": "Дата", "date": {"on_or_before": date_to}},
    ]})
    if err:
        send(token, chat_id, f"Notion: {err}"); return
    if not pages:
        send(token, chat_id, "На 7 днів нічого немає."); return
    lines = ["*План на 7 днів:*\n"]
    for p in pages:
        post = parse_post(p)
        props = p.get("properties", {})
        d2 = props.get("Дата", {}).get("date")
        date_str = d2.get("start", "?")[:10] if d2 else "?"
        lines.append(f"• {date_str} [{post['status'] or '-'}] {post['name'] or 'Без назви'}")
    send(token, chat_id, "\n".join(lines))


def _cmd_today(token, notion_token, db_ids, chat_id):
    today = datetime.now().strftime("%Y-%m-%d")
    pages, err = notion_query(notion_token, db_ids["content_plan"],
        filter_body={"property": "Дата", "date": {"equals": today}})
    if err:
        send(token, chat_id, f"Notion: {err}"); return
    if not pages:
        send(token, chat_id, "На сьогодні нічого."); return
    lines = ["*Сьогодні:*\n"]
    for p in pages:
        post = parse_post(p)
        lines.append(f"• [{post['status'] or '-'}] {post['name'] or 'Без назви'}")
    send(token, chat_id, "\n".join(lines))

# ─── POLLING ────────────────────────────────────────────────────────────────

def run_polling(token, notion_token, db_ids, blog_token, blog_db,
                channel_id, admin_chat_id, env):
    offset = None
    print(f"[bot] Started | admin={admin_chat_id} | channel={channel_id}")
    print(f"[bot] Blog DB: {'OK' if blog_db else 'not configured'}")
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=30"
            if offset is not None:
                url += f"&offset={offset}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read())

            for upd in data.get("result", []):
                offset = upd["update_id"] + 1

                if "callback_query" in upd:
                    from_id = upd["callback_query"]["from"]["id"]
                    if str(from_id) == str(admin_chat_id):
                        handle_callback(
                            token, notion_token, db_ids,
                            blog_token, blog_db,
                            channel_id, admin_chat_id, env, upd
                        )
                    continue

                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                if str(msg["chat"]["id"]) != str(admin_chat_id):
                    continue
                handle_message(token, notion_token, db_ids, channel_id, admin_chat_id, env, msg)

        except urllib.error.URLError as e:
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                continue
            print(f"[bot] URLError: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[bot] Stopped.")
            break
        except Exception as e:
            print(f"[bot] Error: {e}")
            time.sleep(5)

# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    env          = load_env()
    token        = env.get("TELEGRAM_BOT_TOKEN", "")
    notion_token = env.get("NOTION_TOKEN", "")
    blog_token   = env.get("NOTION_BLOG_TOKEN", "")
    blog_db      = env.get("NOTION_BLOG_DB_ID", "")
    channel_id   = env.get("TELEGRAM_CHANNEL_ID", "@prodayslonakume")
    admin_chat_id = env.get("TELEGRAM_ADMIN_CHAT_ID", "")

    if not token or not notion_token:
        print("[ERR] Потрібні TELEGRAM_BOT_TOKEN та NOTION_TOKEN у .env"); sys.exit(1)
    if not admin_chat_id:
        print("[ERR] Потрібен TELEGRAM_ADMIN_CHAT_ID у .env"); sys.exit(1)

    db_ids = load_db_ids()

    # Перевірка при старті
    check_and_send_posts(token, notion_token, db_ids, admin_chat_id)
    check_and_send_blog_articles(token, blog_token, blog_db, admin_chat_id)

    # Фоновий scheduler кожні 5 хв
    t = threading.Thread(
        target=scheduler_loop,
        args=(token, notion_token, db_ids, blog_token, blog_db, admin_chat_id, 300),
        daemon=True,
    )
    t.start()

    run_polling(token, notion_token, db_ids, blog_token, blog_db,
                channel_id, admin_chat_id, env)

if __name__ == "__main__":
    main()
