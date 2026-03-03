# -*- coding: utf-8 -*-
"""
planfix_tg_monitor.py — Моніторинг Telegram каналів Planfix.

Канали:
  @planfixua          — новини Planfix для України (публічний)
  @planfix_details_ru — технічні деталі для розробників (публічний)

Логіка:
  • Кожен пост оцінюється Claude: чи варто публікувати?
  • Якщо значна новина  → розгортає у повну статтю → Notion Blog DB
  • Якщо коротке оновлення → TG пост "На затвердженні" → content_plan
  • Пости з @planfixua перевіряються проти вже оброблених (уникнення дублів із блогу)
  • Developer-only пости з @planfix_details_ru → технічний блог або пропуск

Запуск: python scripts/planfix_tg_monitor.py
"""
import io, sys, json, os, time, re
import urllib.request, urllib.error, urllib.parse
from datetime import date

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
PROCESSED_FILE = os.path.join(DATA_DIR, 'processed_tg_posts.json')

# TG канали для моніторингу
TG_CHANNELS = [
    {'handle': 'planfixua',          'label': 'Planfix UA (новини)',  'type': 'news'},
    {'handle': 'planfix_details_ru', 'label': 'Planfix Details (dev)', 'type': 'dev'},
]

MAX_POSTS_PER_CHANNEL = 20  # Скільки постів перевіряємо з кожного каналу
MAX_NEW_PER_RUN = 4         # Скільки нових постів обробляємо за запуск

# ============================================================
# ENV / CONFIG
# ============================================================

def load_env():
    env = {}
    env_path = os.path.join(ROOT, '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    else:
        env = dict(os.environ)
    return env

def load_db_ids():
    with open(os.path.join(ROOT, 'NOTION_DATABASE_IDS.json'), encoding='utf-8') as f:
        return json.load(f)

# ============================================================
# HTTP
# ============================================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'uk,ru;q=0.9,en;q=0.7',
    'Accept-Encoding': 'identity',
}

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        try:
            return raw.decode('utf-8', errors='replace'), r.url
        except Exception:
            return raw.decode('latin-1', errors='replace'), r.url

# ============================================================
# TELEGRAM WEB PARSER (t.me/s/channel)
# ============================================================

def parse_tg_channel(channel_handle, limit=MAX_POSTS_PER_CHANNEL):
    """
    Завантажує публічні пости каналу через t.me/s/channel.
    Повертає список {id, text, date} (від найновіших).
    """
    url = f'https://t.me/s/{channel_handle}'
    try:
        html, _ = fetch(url, timeout=25)
    except Exception as e:
        print(f'  ERR fetch {url}: {e}')
        return []

    # Розбиваємо HTML на блоки по data-post
    # Кожен пост має: data-post="channel/123"
    blocks = re.split(r'(?=data-post=["\'])', html)

    posts = []
    for block in blocks[1:]:  # перший — заголовок сторінки
        # ID поста
        id_m = re.match(r'data-post=["\']([^"\']+)["\']', block)
        if not id_m:
            continue
        post_id = id_m.group(1)

        # Текст поста (клас tgme_widget_message_text)
        text_m = re.search(
            r'class=["\']tgme_widget_message_text[^"\']*["\'][^>]*>(.*?)</div>',
            block, re.DOTALL | re.IGNORECASE
        )
        if not text_m:
            continue
        raw_html = text_m.group(1)

        # Замінюємо <br> на пробіл, прибираємо теги
        raw_html = re.sub(r'<br\s*/?>', ' ', raw_html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', raw_html)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = ' '.join(text.split()).strip()

        if len(text) < 30:  # Занадто короткий — ігноруємо
            continue

        # Дата
        date_m = re.search(r'datetime=["\']([^"\']+)["\']', block)
        post_date = date_m.group(1)[:10] if date_m else str(date.today())

        posts.append({
            'id': post_id,
            'text': text,
            'date': post_date,
            'url': f'https://t.me/{post_id}',
        })

    return posts[:limit]

# ============================================================
# CLAUDE API
# ============================================================

def claude(api_key, system_p, user_p, max_tokens=3000):
    body = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': max_tokens,
        'system': system_p,
        'messages': [{'role': 'user', 'content': user_p}],
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages', data=body,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }, method='POST')
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())['content'][0]['text']


EVAL_SYSTEM = (
    "Ти контент-менеджер CRMCUSTOMS (crmcustoms.com). "
    "Ми — партнер Planfix в Україні. Пишемо від першої особи компанії. "
    "Без посилань на джерела, без згадки про Telegram-канали."
)

EVAL_PROMPT = """\
Telegram пост з Planfix каналу. Оціни та обробви.

ПОСТ:
{text}
Дата: {date}
Тип каналу: {channel_type}

━━━ КРОК 1: ОЦІНКА ━━━

Визнач:
1. Чи варто публікувати? Критерії для ПРОПУСКУ:
   • Чисто технічне (API, вебхуки, SDK) для розробників — не для блогу власників бізнесу
   • РФ-специфічний контент (Сбербанк, СДЕК, Яндекс, hh.ru тощо)
   • Рекламний спам або оголошення без контентної цінності
   • Занадто короткий/незрозумілий без контексту

2. Формат публікації:
   "article" — є достатньо інфо для повноцінної статті 500+ слів
               (опис функції, кейс, how-to, порівняння)
   "post"    — коротка новина, анонс, оновлення → TG пост для схвалення

━━━ КРОК 2: ГЕНЕРАЦІЯ ━━━

Для "article" (500-800 слів):
  Розгорни у повну статтю для crmcustoms.com від імені CRMCUSTOMS.
  "news" — функція Planfix → що це, як працює, що дає бізнесу
  "case"/"dev" → як це застосувати, практичний приклад

Для "post" (50-80 слів):
  TG пост для @prodayslonakume:
  🔹 *Заголовок*
  (пустий рядок)
  Текст...

ПРАВИЛА SLUG: лише малі латинські, цифри, дефіс.
Транслітерація: а=a б=b в=v г=h д=d е=e є=ye ж=zh з=z и=y і=i ї=yi й=y к=k л=l
м=m н=n о=o п=p р=r с=s т=t у=u ф=f х=kh ц=ts ч=ch ш=sh щ=shch ю=yu я=ya

━━━ ВІДПОВІДЬ: ТІЛЬКИ JSON (без ```json) ━━━

Якщо skip=true:
{{"skip": true, "skip_reason": "коротка причина"}}

Якщо format="article":
{{
  "skip": false,
  "format": "article",
  "h1": "H1 до 70 символів",
  "h2": "H2 до 60 символів",
  "h2_list": ["Розділ 1", "Розділ 2", "Розділ 3"],
  "title_seo": "SEO Title | CRMCUSTOMS",
  "description": "Meta опис 120-160 символів",
  "slug": "url-slug",
  "keywords": "ключ1, ключ2, ключ3, ключ4",
  "lsi_keywords": "lsi1, lsi2, lsi3",
  "image_prompt": "Concrete visual scene (12-18 English words): [who] + [specific action] + [environment] + [mood/light]. Example: smiling manager showing colorful Kanban board to colleagues in sunny open-space office",
  "sections": [
    {{"type": "heading", "text": "Заголовок"}},
    {{"type": "paragraph", "text": "Текст абзацу"}}
  ]
}}

Якщо format="post":
{{
  "skip": false,
  "format": "post",
  "title": "Коротка назва для Notion (до 80 символів)",
  "tg_text": "Текст TG поста з emoji та Markdown"
}}
"""


def claude_evaluate_tg_post(api_key, post, channel_type):
    prompt = EVAL_PROMPT.format(
        text=post['text'][:2000],
        date=post['date'],
        channel_type=channel_type,
    )
    raw = claude(api_key, EVAL_SYSTEM, prompt, max_tokens=3200)
    m = re.search(r'\{[\s\S]+\}', raw)
    if not m:
        raise ValueError(f'Немає JSON:\n{raw[:200]}')
    return json.loads(m.group())

# ============================================================
# FLUX IMAGE GENERATION (через n8n webhook, під капотом — Flux via Replicate)
# ============================================================

def get_flux_image(n8n_url, image_prompt, timeout=90):
    """
    Викликає n8n webhook для генерації обкладинки через Flux.
    Webhook: GET {n8n_url}?text={image_prompt}
    Відповідь: JSON масив, поле "public_link" = S3 URL зображення.
    Повертає: S3 URL або None.
    """
    if not n8n_url or not image_prompt:
        return None
    try:
        encoded = urllib.parse.quote(image_prompt, safe='')
        url = f"{n8n_url.rstrip('/')}?text={encoded}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'CRMCustoms-ContentBot/1.0',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                data = json.loads(raw)
            except Exception:
                text = raw.decode('utf-8', errors='replace').strip().strip('"')
                return text if text.startswith('http') else None
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict):
                for key in ('public_link', 'Location', 'url', 'imageUrl', 'image_url', 'imageURL', 'output', 'result'):
                    val = data.get(key, '')
                    if isinstance(val, str) and val.startswith('http'):
                        return val
                    if isinstance(val, list) and val and isinstance(val[0], str):
                        return val[0]
                for v in data.values():
                    if isinstance(v, str) and v.startswith('https://s3.'):
                        return v
            return None
    except Exception as e:
        print(f'  [image] Flux webhook error: {e}')
        return None

# ============================================================
# NOTION API
# ============================================================

def notion_req(token, method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    req = urllib.request.Request(
        'https://api.notion.com/v1' + path, data=data,
        headers={
            'Authorization': 'Bearer ' + token,
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json',
        }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
    except Exception as e:
        return None, str(e)


def rt(text, limit=2000):
    text = str(text)
    return [{'type': 'text', 'text': {'content': text[i:i+limit]}}
            for i in range(0, len(text), limit)] if text else [{'type': 'text', 'text': {'content': ''}}]


def make_blocks(sections):
    blocks = []
    for s in sections:
        t = s.get('type', '')
        if t == 'heading':
            bt = 'heading_2' if s.get('level', 2) <= 2 else 'heading_3'
            blocks.append({'object': 'block', 'type': bt,
                           bt: {'rich_text': [{'type': 'text', 'text': {'content': s['text'][:2000]}}]}})
        elif t == 'paragraph':
            text = s['text']
            for i in range(0, len(text), 2000):
                blocks.append({'object': 'block', 'type': 'paragraph',
                               'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': text[i:i+2000]}}]}})
    return blocks[:98]


def create_blog_article(blog_token, blog_db, seo, img_url='', author_id=''):
    # Важливі поля: Title, description, linkName (slug), Фото 2 соц (og:image), Ключі, LSI keywords, Дата, Status
    # Фото 2 соц → property_2 в n8n → og:image на сайті (ОСНОВНЕ зображення)
    # photo1     → property_photo1 в n8n → запасне зображення
    # H1/H2/H3 — заповнюємо для повноти але не критичні (тіло = blocks)
    props = {
        '\ufeffName':      {'title': rt(seo.get('h1', '')[:100])},
        'Title':           {'rich_text': rt(seo.get('title_seo', '')[:200])},
        'description':     {'rich_text': rt(seo.get('description', '')[:300])},
        'linkName':        {'rich_text': rt(seo.get('slug', '')[:100])},
        'Фото 2 соц':      {'rich_text': rt((img_url or '')[:500])},  # og:image (property_2) — ОСНОВНЕ
        'photo1':          {'rich_text': rt((img_url or '')[:500])},  # запасне (property_photo1)
        'Ключі':           {'rich_text': rt(seo.get('keywords', '')[:500])},
        'LSI keywords':    {'rich_text': rt(seo.get('lsi_keywords', '')[:500])},
        'H1':              {'rich_text': rt(seo.get('h1', '')[:2000])},
        'H2':              {'rich_text': rt(seo.get('h2', '')[:2000])},
        'H3':              {'rich_text': rt(seo.get('h3', '')[:2000])},
        'Дата публікації': {'date': {'start': str(date.today())}},
        'Публиковать':     {'checkbox': False},
        'Status':          {'multi_select': [{'name': 'Готово до публікації'}]},
    }
    if author_id:
        props['Автори'] = {'relation': [{'id': author_id}]}
    blocks = make_blocks(seo.get('sections', []))
    return notion_req(blog_token, 'POST', '/pages', {
        'parent': {'database_id': blog_db},
        'properties': props,
        'children': blocks,
    })


def save_tg_post(main_token, content_plan_db, title, text):
    return notion_req(main_token, 'POST', '/pages', {
        'parent': {'database_id': content_plan_db},
        'properties': {
            'Назва':       {'title': rt(title[:100])},
            'Текст посту': {'rich_text': rt(text)},
            'Статус':      {'select': {'name': 'На затвердженні'}},
            'Тип':         {'select': {'name': 'Піст'}},
            'Платформи':   {'multi_select': [{'name': 'Telegram'}]},
        }
    })

# ============================================================
# SLUG DEDUP (перевірка чи стаття вже є в Blog DB)
# ============================================================

def get_existing_slugs(token, db_id):
    """Повертає set() усіх linkName (slug) з Blog DB — щоб уникнути дублів."""
    slugs = set()
    cursor = None
    while True:
        body = {'page_size': 100}
        if cursor:
            body['start_cursor'] = cursor
        data, err = notion_req(token, 'POST', f'/databases/{db_id}/query', body)
        if err or not data:
            break
        for page in data.get('results', []):
            prop = page.get('properties', {}).get('linkName', {})
            rtl = prop.get('rich_text', [])
            if rtl:
                slug = rtl[0].get('plain_text', '')
                if slug:
                    slugs.add(slug)
        if not data.get('has_more'):
            break
        cursor = data.get('next_cursor')
    return slugs

# ============================================================
# PROCESSED TRACKER
# ============================================================

def load_processed():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_processed(ids):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)

# ============================================================
# MAIN
# ============================================================

def main():
    env = load_env()
    api_key    = env.get('ANTHROPIC_API_KEY', '')
    blog_token = env.get('NOTION_BLOG_TOKEN', '')
    blog_db    = env.get('NOTION_BLOG_DB_ID', '')
    main_token = env.get('NOTION_TOKEN', '')

    ids = load_db_ids()
    content_plan_db = ids.get('content_plan', '')

    errors = [k for k, v in [
        ('ANTHROPIC_API_KEY', api_key),
        ('NOTION_BLOG_TOKEN', blog_token),
        ('NOTION_BLOG_DB_ID', blog_db),
        ('NOTION_TOKEN', main_token),
    ] if not v]
    if errors:
        print(f'[ERR] Не заповнено в .env: {", ".join(errors)}')
        return

    processed      = load_processed()
    existing_slugs = get_existing_slugs(blog_token, blog_db)
    print(f'Blog DB: вже {len(existing_slugs)} статей (перевірка дублів активна)')

    total_new = 0
    total_done = 0
    total_skip = 0

    print(f'\n=== Моніторинг Telegram каналів Planfix ===\n')

    for channel in TG_CHANNELS:
        handle = channel['handle']
        label  = channel['label']
        ctype  = channel['type']

        print(f'--- {label} (@{handle}) ---')
        posts = parse_tg_channel(handle)
        if not posts:
            print(f'  Постів не знайдено (канал закритий або помилка мережі)')
            print()
            continue

        new_posts = [p for p in posts if p['id'] not in processed]
        print(f'  Постів у стрічці: {len(posts)}  |  Нових: {len(new_posts)}')

        if not new_posts:
            print('  Немає нових постів.')
            print()
            continue

        total_new += len(new_posts)
        channel_done = 0

        for i, post in enumerate(new_posts):
            if total_done >= MAX_NEW_PER_RUN:
                print(f'  Ліміт {MAX_NEW_PER_RUN} постів за запуск досягнуто.')
                break

            print(f'\n  [{i+1}] {post["text"][:65]}...')
            print(f'       Дата: {post["date"]}  |  URL: {post["url"]}')

            try:
                result = claude_evaluate_tg_post(api_key, post, ctype)
            except Exception as e:
                print(f'  ERR Claude: {e}')
                processed.add(post['id'])
                save_processed(processed)
                continue

            if result.get('skip'):
                reason = result.get('skip_reason', 'не підходить')
                print(f'  SKIP: {reason}')
                processed.add(post['id'])
                save_processed(processed)
                total_skip += 1
                continue

            fmt = result.get('format', 'post')

            if fmt == 'article':
                slug = result.get('slug', '')
                print(f'  → Стаття: "{result.get("h1", "")[:50]}"  slug: {slug}')
                # Перевірка дублів
                if slug and slug in existing_slugs:
                    print(f'  SKIP: slug "{slug}" вже є в Blog DB')
                    processed.add(post['id'])
                    save_processed(processed)
                    total_skip += 1
                    continue
                # Генерація обкладинки через Flux
                # Writer Agent видалено з n8n → передаємо Image Prompt Agent повний контекст
                flux_url     = env.get('FLUX_BLOG_WEBHOOK_URL', '')
                image_prompt = result.get('image_prompt', '')
                img_url = ''
                if flux_url and image_prompt:
                    flux_text = f"{result.get('h1', '')}. {result.get('description', '')} | {image_prompt}"
                    print(f'  [img] Flux: {flux_text[:65]}...')
                    img_url = get_flux_image(flux_url, flux_text) or ''
                    if img_url:
                        print(f'  [img] OK: {img_url[:60]}')
                    else:
                        print(f'  [img] WARN: не отримано — стаття без обкладинки')
                res, err = create_blog_article(blog_token, blog_db, result, img_url=img_url)
                if err:
                    print(f'  ERR Notion Blog: {err}')
                else:
                    print(f'  OK → Notion Blog ({slug})')
                    if slug:
                        existing_slugs.add(slug)
                    total_done += 1
                    channel_done += 1

            elif fmt == 'post':
                tg_text = result.get('tg_text', '')
                title   = result.get('title', post['text'][:70])
                print(f'  → TG пост: "{title[:50]}"')
                if content_plan_db:
                    _, err = save_tg_post(main_token, content_plan_db, title, tg_text)
                    if err:
                        print(f'  ERR Notion: {err}')
                    else:
                        print('  OK → content_plan (На затвердженні)')
                        total_done += 1
                        channel_done += 1
                else:
                    print('  WARN: content_plan DB не налаштовано')

            processed.add(post['id'])
            save_processed(processed)
            time.sleep(2)

        print(f'\n  Канал @{handle}: оброблено {channel_done}')
        print()

    print(f'=== Підсумок: нових постів {total_new}, оброблено {total_done}, пропущено {total_skip} ===')
    if total_done:
        print('Перевір content_plan (TG пости) та Notion Blog DB (статті).')


if __name__ == '__main__':
    main()
