# -*- coding: utf-8 -*-
"""
planfix_to_blog.py — Моніторинг блогу Planfix → рерайт → Notion Blog DB.

Два режими:
  --news   planfix.com (UA-сайт) → новини/функції → без РФ-фільтру
           Джерело: PLANFIX_NEWS_URL з .env
  --cases  planfix.ru blog → кейси та приклади → з РФ-фільтром
           Джерело: PLANFIX_CASES_URL з .env
  (без флагу) — спочатку news, потім cases

Запуск:
  python scripts/planfix_to_blog.py          ← обидва джерела
  python scripts/planfix_to_blog.py --news   ← тільки новини planfix.com
  python scripts/planfix_to_blog.py --cases  ← тільки кейси planfix.ru
  python scripts/planfix_to_blog.py <URL>    ← конкретна стаття (тест)
"""
import io, sys, json, os, time, re
import urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from datetime import date

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
PROCESSED_FILE = os.path.join(DATA_DIR, 'processed_planfix_urls.json')

MAX_PER_RUN = 3  # Статей за один запуск

# ============================================================
# КАТЕГОРІЇ Notion Blog DB (перевірено через API 01.03.2026)
# ============================================================
CATEGORY_MAP = {
    'Новини':        '62bf2f64-c91b-416b-950c-28f026f24f4c',
    'Кейси':         'c87e8f60-022c-431d-9343-020416e7d9ed',
    'Бізнес':        '26a45fe2-54cb-4998-a80f-34ca7ffbb777',
    'Маркетинг':     '88fc873a-6866-404a-9ad7-e87420fe5a73',
    'Автоматизація': '9110c5b6-97bd-495d-bd7f-5370b7a30e0a',
    'Інструменти':   'a9fbc4d3-ba23-4819-9a3f-a35dc3663785',
    'Бібліотека':    '26ff705b-68d3-80d6-b186-c0400b083689',
}

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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'uk,ru;q=0.8,en;q=0.6',
    'Accept-Encoding': 'identity',
}

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ct = r.headers.get('Content-Type', '')
        charset = 'utf-8'
        m = re.search(r'charset=([^\s;,]+)', ct, re.IGNORECASE)
        if m:
            charset = m.group(1).strip().lower().replace('windows-', 'cp').replace('win-', 'cp')
        else:
            meta_m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', raw[:2000])
            if meta_m:
                charset = meta_m.group(1).decode('ascii', 'replace').lower()
                charset = charset.replace('windows-', 'cp').replace('win-', 'cp')
        try:
            return raw.decode(charset, errors='replace'), r.url
        except LookupError:
            return raw.decode('utf-8', errors='replace'), r.url

# ============================================================
# RSS
# ============================================================

def scrape_tg_channel(channel_url):
    """Парсить публічний Telegram канал через t.me/s/CHANNEL.
    Повертає список {'url': ..., 'title': ...} з посиланнями на пости."""
    try:
        s_url = channel_url.rstrip('/').replace('t.me/', 't.me/s/')
        if '/s/' not in s_url:
            s_url = s_url.replace('t.me/', 't.me/s/')
        html, _ = fetch(s_url, timeout=15)
        # Шукаємо посилання на окремі пости: t.me/planfixua/123
        import re as _re
        base = s_url.split('/s/')[0] + '/'
        channel_name = s_url.split('/s/')[-1].split('/')[0]
        # Витягуємо текст постів і їх номери
        posts = []
        # Пости мають data-post="channel/number"
        for m in _re.finditer(
            r'data-post=["\']' + channel_name + r'/(\d+)["\'].*?'
            r'class=["\']tgme_widget_message_text["\'][^>]*>(.*?)</div>',
            html, _re.DOTALL | _re.IGNORECASE
        ):
            num  = m.group(1)
            text = _re.sub(r'<[^>]+>', ' ', m.group(2)).strip()
            text = ' '.join(text.split())[:200]
            url  = f"https://t.me/{channel_name}/{num}"
            if text:
                posts.append({'url': url, 'title': text[:80]})
        if posts:
            print(f'  TG канал {channel_name}: {len(posts)} постів')
        return posts
    except Exception as e:
        print(f'  ERR TG scrape: {e}')
        return []


def try_rss(blog_url):
    parsed = urllib.parse.urlparse(blog_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip('/')
    candidates = [path + c for c in ('/feed', '/rss', '/feed.xml', '/rss.xml')]
    candidates += [base + c for c in ('/feed', '/rss', '/feed.xml', '/rss.xml')]

    for rss_url in candidates:
        try:
            html, _ = fetch(rss_url, timeout=10)
            root_el = ET.fromstring(html.encode('utf-8', errors='replace'))
            items = []
            for item in root_el.findall('.//item'):
                lnk = item.find('link')
                ttl = item.find('title')
                url = (lnk.text or '').strip() if lnk is not None else ''
                title = (ttl.text or '').strip() if ttl is not None else ''
                if url:
                    items.append({'url': url, 'title': title})
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            for entry in root_el.findall('a:entry', ns):
                lnk = entry.find('a:link[@rel="alternate"]', ns) or entry.find('a:link', ns)
                ttl = entry.find('a:title', ns)
                if lnk is not None:
                    href = lnk.get('href', '')
                    title = (ttl.text or '').strip() if ttl is not None else ''
                    if href:
                        items.append({'url': href, 'title': title})
            if items:
                print(f'  RSS: {rss_url} ({len(items)} статей)')
                return items
        except Exception:
            pass
    return []

# ============================================================
# HTML ARTICLE LIST PARSER
# ============================================================

class ArticleListParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.base_netloc = urllib.parse.urlparse(base_url).netloc
        self.base_path = urllib.parse.urlparse(base_url).path.rstrip('/')
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        attrs_d = dict(attrs)
        href = attrs_d.get('href', '')
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            return
        full = urllib.parse.urljoin(self.base_url, href).split('?')[0].split('#')[0]
        p = urllib.parse.urlparse(full)
        if p.netloc != self.base_netloc:
            return
        path = p.path.rstrip('/')
        if path.startswith(self.base_path + '/') and len([x for x in path.split('/') if x]) >= 2:
            self.links.add(full)

def scrape_article_list(url):
    try:
        html, _ = fetch(url)
        parser = ArticleListParser(url)
        parser.feed(html)
        links = sorted(parser.links)
        print(f'  HTML scrape: {len(links)} посилань')
        return [{'url': u, 'title': ''} for u in links]
    except Exception as e:
        print(f'  ERR scrape: {e}')
        return []

# ============================================================
# ARTICLE CONTENT PARSER
# ============================================================

class ArticleContentParser(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'iframe'}
    CONTENT_TAGS = {'article', 'main'}
    CONTENT_KW = ('post-content', 'article-content', 'entry-content', 'blog-post',
                  'post-body', 'article-body', 'content-body', 'single-post',
                  'post__content', 'article__content', 'blog__content', 'rich-text')

    def __init__(self, base_url=''):
        super().__init__()
        self.base_url = base_url
        self.title = ''
        self.first_img = ''
        self.sections = []
        self._d = 0
        self._skip_d = 0
        self._in_main = False
        self._main_d = 0
        self._ctype = ''
        self._clevel = 0
        self._buf = []

    def _is_content(self, tag, attrs_d):
        if tag in self.CONTENT_TAGS:
            return True
        cls = attrs_d.get('class', '').lower()
        id_ = attrs_d.get('id', '').lower()
        return any(kw in cls or kw in id_ for kw in self.CONTENT_KW)

    def handle_starttag(self, tag, attrs):
        self._d += 1
        ad = dict(attrs)
        if tag in self.SKIP:
            self._skip_d = self._d
            return
        if self._skip_d:
            return
        if not self._in_main and self._is_content(tag, ad):
            self._in_main = True
            self._main_d = self._d
            return
        if not self._in_main:
            return
        if tag == 'h1' and not self.title:
            self._flush(); self._start('h1', 1)
        elif tag in ('h2', 'h3', 'h4'):
            self._flush(); self._start('heading', int(tag[1]))
        elif tag == 'p':
            self._flush(); self._start('paragraph', 0)
        elif tag == 'img':
            src = ad.get('src') or ad.get('data-src', '')
            if src and not src.startswith('data:'):
                full = urllib.parse.urljoin(self.base_url, src)
                if not self.first_img:
                    self.first_img = full
                self._flush()
                self.sections.append({'type': 'image', 'text': full})

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip_d = 0
        if self._skip_d:
            self._d -= 1
            return
        if tag in ('h1', 'h2', 'h3', 'h4', 'p'):
            self._flush()
        if self._in_main and self._d <= self._main_d:
            self._in_main = False
        self._d -= 1

    def handle_data(self, data):
        if not self._skip_d and self._in_main and self._ctype:
            self._buf.append(data)

    def _start(self, t, lv):
        self._buf = []; self._ctype = t; self._clevel = lv

    def _flush(self):
        if not self._ctype:
            return
        text = ' '.join(''.join(self._buf).split()).strip()
        if text:
            if self._ctype == 'h1':
                self.title = text
            else:
                self.sections.append({'type': self._ctype, 'text': text, 'level': self._clevel})
        self._buf = []; self._ctype = ''; self._clevel = 0


def parse_article(url):
    html, _ = fetch(url)
    p = ArticleContentParser(url)
    p.feed(html)

    if not p.sections:
        for raw in re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE):
            clean = ' '.join(re.sub(r'<[^>]+>', ' ', raw).split()).strip()
            if len(clean) > 60:
                p.sections.append({'type': 'paragraph', 'text': clean, 'level': 0})

    if not p.first_img:
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)[^>]+property=["\']og:image["\']', html, re.IGNORECASE)
        if m:
            p.first_img = m.group(1)

    if not p.title:
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
        if m:
            p.title = m.group(1).strip()
        else:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            if m:
                p.title = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    return {'title': p.title, 'sections': p.sections, 'first_img': p.first_img, 'url': url}

# ============================================================
# CLAUDE API
# ============================================================

def claude(api_key, system_p, user_p, max_tokens=3500):
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
    "Ти контент-менеджер CRMCUSTOMS — офіційного партнера Planfix в Україні (crmcustoms.com). "
    "Тон: живий, дружній, від компанії-партнера. Мова: проста ділова українська без канцеляриту."
)

EVAL_PROMPT = """\
Planfix опублікував нову статтю/новину. Зроби короткий пост для блогу CRMCUSTOMS.

ОРИГІНАЛ:
Заголовок: {title}
Джерело: {url}

Контент:
{content}

━━━ КРОК 1: ОЦІНКА ━━━

ПРОПУСТИТИ якщо:
  • Стаття не про Planfix (реклама, загальні поради без Planfix)
  • РФ-специфіка: Сбербанк, Яндекс, СДЕК, Wildberries, Ozon, ВТБ, МТС, hh.ru, Авіто тощо

ЗАЛИШИТИ якщо: новина про функцію/оновлення/фічу Planfix, або кейс з глобальними SaaS
(Gmail, Zoom, Slack, WhatsApp, Telegram, Stripe, Zapier, Make тощо).

━━━ КРОК 2: КОРОТКИЙ ПОСТ (тільки якщо skip=false) ━━━

ОБСЯГ: 150-250 слів — не більше!
ТОН: "Planfix молодці — вийшло оновлення X. Ось що це дає вашому бізнесу..."
     Пишемо від CRMCUSTOMS, позитивно про Planfix як партнери.
СТРУКТУРА: 1-2 абзаци суті → що це дає клієнту → (опційно) наш коментар

ЗАБОРОНЕНО:
  • Посилання на джерело, "за даними Planfix", "оригінал статті"
  • Порожні фрази ("це дуже важливо", "варто зазначити")
  • Вигадувати факти яких немає в оригіналі

ІЛЮСТРАЦІЇ (illustration_prompts) — 1 бізнес-сцена для генерації зображення.
  Конкретна візуальна сцена 15-20 англ. слів: хто + дія + середовище.
  Приклад: "Focused manager reviewing CRM pipeline on large monitor in modern Ukrainian office"

UI-СКРІНШОТ (ui_prompts) — тільки якщо стаття про конкретний модуль/функцію Planfix.
  Детальний опис інтерфейсу: назва модуля, колонки, кнопки, кольори, дані у рядках.
  Якщо загальна стаття — залиш [].

SLUG: лише малі латинські + цифри + дефіс. Транслітерація:
а=a б=b в=v г=h д=d е=e є=ye ж=zh з=z и=y і=i ї=yi й=y к=k л=l м=m н=n о=o п=p
р=r с=s т=t у=u ф=f х=kh ц=ts ч=ch ш=sh щ=shch ю=yu я=ya пробіл=- апостроф=нічого

━━━ ВІДПОВІДЬ: ТІЛЬКИ JSON без ```json ━━━

Якщо skip=true:
{{"skip": true, "skip_reason": "коротка причина"}}

Якщо skip=false:
{{
  "skip": false,
  "h1": "Заголовок до 70 символів",
  "title_seo": "SEO Title до 60 символів | CRMCUSTOMS",
  "description": "Meta description 120-160 символів",
  "slug": "url-slug-transliterovanyi",
  "category": "Новини",
  "illustration_prompts": ["Concrete business scene 15-20 English words"],
  "ui_prompts": [],
  "sections": [
    {{"type": "heading", "text": "Заголовок секції"}},
    {{"type": "paragraph", "text": "Текст 150-250 слів"}}
  ]
}}
"""

TG_ANNOUNCE_PROMPT = """\
Напиши анонс для Telegram каналу @prodayslonakume про нову статтю.

Стаття: {h1}
Опис: {description}
Посилання: {site_url}

Формат:
🔹 *Заголовок-хук* (1 рядок)

2-3 речення: суть статті і навіщо читати

📖 Читати: {site_url}

Правила: українська, 50-70 слів, Telegram Markdown, без хештегів.
Виведи ТІЛЬКИ текст поста."""


def claude_eval_and_rewrite(api_key, article):
    parts = []
    for s in article['sections'][:40]:
        if s['type'] == 'heading':
            parts.append(f"\n## {s['text']}\n")
        elif s['type'] == 'paragraph':
            parts.append(s['text'])
    content = '\n'.join(parts)[:4000]

    prompt = EVAL_PROMPT.format(
        title=article['title'],
        url=article['url'],
        content=content,
    )
    raw = claude(api_key, EVAL_SYSTEM, prompt, max_tokens=3800)
    m = re.search(r'\{[\s\S]+\}', raw)
    if not m:
        raise ValueError(f'Немає JSON у відповіді Claude:\n{raw[:300]}')
    return json.loads(m.group())


def claude_tg_announce(api_key, seo, site_url):
    prompt = TG_ANNOUNCE_PROMPT.format(
        h1=seo.get('h1', ''),
        description=seo.get('description', ''),
        site_url=site_url,
    )
    return claude(api_key, '', prompt, max_tokens=400)

# ============================================================
# FLUX IMAGE GENERATION (через n8n webhook, під капотом — Flux via Replicate)
# ============================================================

def is_image_accessible(url, timeout=10):
    """Перевіряє доступність зображення через HEAD-запит.
    Повертає True якщо HTTP 200-299, False для 403/404/помилок/redirect-на-заглушку."""
    if not url or not url.startswith('http'):
        return False
    try:
        req = urllib.request.Request(url, headers=HEADERS, method='HEAD')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ct = r.headers.get('Content-Type', '').lower()
            # Якщо повернули HTML — це редирект на заглушку, а не зображення
            if 'text/html' in ct:
                return False
            return 200 <= r.status < 300
    except urllib.error.HTTPError:
        return False
    except Exception:
        # HEAD може бути заблокований — спробуємо GET з обмеженням (перші 512 байт)
        try:
            req2 = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req2, timeout=timeout) as r:
                ct = r.headers.get('Content-Type', '').lower()
                r.read(512)  # тільки заголовки + початок
                return 200 <= r.status < 300 and 'text/html' not in ct
        except Exception:
            return False


def get_flux_image(n8n_url, image_prompt, timeout=90):
    """
    Викликає n8n webhook для генерації обкладинки через Flux.
    Webhook: GET ?text={image_prompt}
    n8n chain (без Writer Agent): Image Prompt Agent (GPT-4.1 ~8s)
               → Flux 1.1 Pro Ultra (~25s) → S3 upload → відповідь
    Відповідь: JSON масив, поле "public_link" = S3 URL зображення.
    Повертає: рядок S3 URL або None при помилці.
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

            # Відповідь може бути масивом (n8n allIncomingItems) або одним об'єктом
            if isinstance(data, list) and data:
                data = data[0]

            if isinstance(data, dict):
                # Пріоритет: відомі поля з URL зображення
                for key in ('public_link', 'Location', 'url', 'imageUrl', 'image_url', 'imageURL', 'output', 'result'):
                    val = data.get(key, '')
                    if isinstance(val, str) and val.startswith('http'):
                        return val
                    if isinstance(val, list) and val and isinstance(val[0], str):
                        return val[0]
                # Крайній fallback: перше поле з http
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
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}"
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
        elif t == 'image' and s.get('text', '').startswith('http'):
            blocks.append({'object': 'block', 'type': 'image',
                           'image': {'type': 'external', 'external': {'url': s['text']}}})
    return blocks[:98]


def get_existing_slugs(token, db_id):
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


def inject_illustrations(sections, urls):
    """Вставляє ілюстрації після 2-го і 4-го heading блоків (якщо є)."""
    if not urls:
        return sections
    # Позиції всіх heading-секцій (крім першої — вона йде одразу після обкладинки)
    heading_positions = [i for i, s in enumerate(sections) if s.get('type') == 'heading']
    insert_targets = heading_positions[1:]  # після 2-го heading, 4-го heading тощо
    result = list(sections)
    offset = 0
    for url, pos in zip(urls, insert_targets):
        result.insert(pos + offset, {'type': 'image', 'text': url})
        offset += 1
    return result


def send_tg(token, chat_id, text):
    """Надсилає повідомлення в Telegram."""
    if not token or not chat_id:
        return
    try:
        body = json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}).encode('utf-8')
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data=body, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f'  [TG] не вдалося відправити звіт: {e}')


def notion_create_blog_page(token, db_id, seo, img_url, author_id=''):
    """Створює сторінку у Notion Blog DB.
    Важливі поля (перевірено через API 01.03.2026):
      - linkName (slug) → URL сторінки на сайті (КРИТИЧНО)
      - Title → <title> тег (SEO)
      - description → meta description (SEO)
      - Фото 2 соц → og:image / head зображення (property_2 в n8n — ОСНОВНЕ)
      - photo1 → запасне зображення (property_photo1 в n8n)
      - Ключі, LSI keywords → SEO ключові слова
      - Дата публікації → сортування на сайті
      - Публиковать + Status → контролюють видимість
      - Автори → relation (Ткаченко Максим)
    H1/H2/H3 — заповнюємо для повноти але сайт їх не потребує (тіло = blocks)
    """
    env = load_env()
    if not author_id:
        author_id = env.get('BLOG_AUTHOR_ID', '')

    props = {
        '\ufeffName':      {'title': rt(seo.get('h1', '')[:100])},
        # SEO-поля (важливі для сайту)
        'Title':           {'rich_text': rt(seo.get('title_seo', '')[:200])},
        'description':     {'rich_text': rt(seo.get('description', '')[:300])},
        'linkName':        {'rich_text': rt(seo.get('slug', '')[:100])},      # URL slug — КРИТИЧНО
        'Фото 2 соц':      {'rich_text': rt((img_url or '')[:500])},          # og:image (property_2) — ОСНОВНЕ
        'photo1':          {'rich_text': rt((img_url or '')[:500])},          # запасне (property_photo1)
        'Ключі':           {'rich_text': rt(seo.get('keywords', '')[:500])},
        'LSI keywords':    {'rich_text': rt(seo.get('lsi_keywords', '')[:500])},
        # H1/H2/H3 — для повноти (не критичні, тіло статті = blocks)
        'H1':              {'rich_text': rt(seo.get('h1', '')[:2000])},
        'H2':              {'rich_text': rt(seo.get('h2', '')[:2000])},
        'H3':              {'rich_text': rt(seo.get('h3', '')[:2000])},
        # Системні поля
        'Дата публікації': {'date': {'start': str(date.today())}},
        'Публиковать':     {'checkbox': False},
        'Status':          {'multi_select': [{'name': 'Готово до публікації'}]},
    }
    # Автор (relation)
    if author_id:
        props['Автори'] = {'relation': [{'id': author_id}]}
    # Категорія (relation)
    cat_id = CATEGORY_MAP.get(seo.get('category', ''), '')
    if cat_id:
        props['Category'] = {'relation': [{'id': cat_id}]}

    blocks = make_blocks(seo.get('sections', []))
    return notion_req(token, 'POST', '/pages', {
        'parent': {'database_id': db_id},
        'properties': props,
        'children': blocks,
    })


def notion_save_tg_post(token, db_id, title, text):
    return notion_req(token, 'POST', '/pages', {
        'parent': {'database_id': db_id},
        'properties': {
            'Назва':       {'title': rt(title[:100])},
            'Текст посту': {'rich_text': rt(text)},
            'Статус':      {'select': {'name': 'На затвердженні'}},
            'Тип':         {'select': {'name': 'Піст'}},
            'Платформи':   {'multi_select': [{'name': 'Telegram'}]},
        }
    })

# ============================================================
# PROCESSED TRACKER
# ============================================================

def load_processed():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_processed(urls):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted(urls), f, ensure_ascii=False, indent=2)

# ============================================================
# CORE PROCESSOR
# ============================================================

def process_article(url, api_key, blog_token, blog_db,
                    main_token, content_plan_db, existing_slugs=None):
    """Обробляє одну статтю. Повертає 'ok' | 'skip' | 'error'."""
    try:
        env = load_env()
        author_id = env.get('BLOG_AUTHOR_ID', '')

        # 1. Завантажити статтю
        print('  [1/3] Завантажую...')
        article = parse_article(url)
        if not article['sections']:
            print('  SKIP: порожній контент')
            return 'skip'
        print(f'  Заголовок: {(article["title"] or "?")[:55]}')
        print(f'  Розділів:  {len(article["sections"])}  |  Фото: {"є" if article["first_img"] else "немає"}')

        # 2. Claude: оцінка + рерайт
        print('  [2/3] Claude: оцінка + рерайт...')
        seo = claude_eval_and_rewrite(api_key, article)

        if seo.get('skip'):
            reason = seo.get('skip_reason', 'РФ-специфічний контент')
            print(f'  SKIP: {reason}')
            return 'skip'

        ctype = seo.get('type', 'news')
        print(f'  Тип:  {ctype}')
        print(f'  H1:   {seo.get("h1", "")[:55]}')
        print(f'  Slug: {seo.get("slug", "")}')

        if existing_slugs is not None and seo.get('slug') in existing_slugs:
            print('  SKIP: slug вже існує')
            return 'skip'

        # ── Обкладинка: беремо з джерела (Planfix вже має хороші зображення) ──
        img_url = ''
        source_img = article.get('first_img', '') or ''
        is_placeholder = any(x in source_img for x in (
            'transparent', 'placeholder', '/themes/', '1x1', 'spacer', 'blank'
        ))
        if source_img and not is_placeholder and is_image_accessible(source_img):
            img_url = source_img
            print(f'  [cover] ✓ Фото зі статті: {img_url[:65]}')
        else:
            print(f'  [cover] Фото не знайдено або недоступне')
        # ──────────────────────────────────────────────────────────────────

        # Зберігаємо illustration_prompts та ui_prompts у логах (для майбутньої генерації)
        illustration_prompts = seo.get('illustration_prompts', [])
        ui_prompts = seo.get('ui_prompts', [])
        if illustration_prompts:
            print(f'  [prompts] illustration: {illustration_prompts[0][:80]}')
        if ui_prompts:
            print(f'  [prompts] ui: {ui_prompts[0][:80]}')

        seo_final = dict(seo)

        # 3. Notion Blog DB
        # Бот потім надішле на схвалення. Після схвалення → Завершено + Публиковать=True + авто TG анонс
        print('  [3/3] Зберігаю в Notion Blog (Готово до публікації)...')
        result, err = notion_create_blog_page(blog_token, blog_db, seo_final, img_url, author_id)
        if err:
            print(f'  ERR Notion: {err}')
            return 'error'
        notion_url = result.get('url', '')
        print(f'  OK → {notion_url[:65] if notion_url else "сторінку створено"}')
        print('  → Бот надішле тобі на схвалення (перевір /check)')

        return 'ok'

    except Exception as e:
        import traceback
        print(f'  ERR: {e}')
        lines = [l for l in traceback.format_exc().split('\n') if l.strip()]
        print('  ' + '\n  '.join(lines[-3:]))
        return 'error'

# ============================================================
# MAIN
# ============================================================

def run_source(source_url, source_label,
               api_key, blog_token, blog_db, main_token, content_plan_db,
               processed, existing_slugs):
    """Обробляє одне джерело статей. Оновлює processed і existing_slugs на місці."""
    print(f'\n=== {source_label} ===')
    print(f'URL: {source_url}  |  Ліміт: {MAX_PER_RUN} статей/запуск\n')

    articles = try_rss(source_url)
    if not articles:
        print('RSS не знайдено, пробую HTML scraping...')
        articles = scrape_article_list(source_url)
    if not articles:
        print('[WARN] Статей не знайдено.')
        return 0, 0, 0

    new_arts = [a for a in articles if a['url'] not in processed]
    print(f'Знайдено: {len(articles)}  |  Нових: {len(new_arts)}  |  Обробляємо: {min(len(new_arts), MAX_PER_RUN)}\n')

    if not new_arts:
        print('Нових статей немає.')
        return 0, 0, 0

    done = skipped = errors_cnt = 0
    for i, art in enumerate(new_arts[:MAX_PER_RUN], 1):
        label = art.get('title') or art['url'].split('/')[-2] or art['url'][:55]
        print(f'--- [{i}/{min(len(new_arts), MAX_PER_RUN)}] {label[:60]} ---')
        result = process_article(
            art['url'], api_key, blog_token, blog_db,
            main_token, content_plan_db, existing_slugs
        )
        processed.add(art['url'])
        save_processed(processed)
        if result == 'ok':     done += 1
        elif result == 'skip': skipped += 1
        else:                  errors_cnt += 1
        print()
        time.sleep(3)

    return done, skipped, errors_cnt


def main():
    env = load_env()
    api_key    = env.get('ANTHROPIC_API_KEY', '')
    blog_token = env.get('NOTION_BLOG_TOKEN', '')
    blog_db    = env.get('NOTION_BLOG_DB_ID', '')
    main_token = env.get('NOTION_TOKEN', '')
    tg_token   = env.get('TELEGRAM_BOT_TOKEN', '')
    tg_admin   = env.get('TELEGRAM_ADMIN_CHAT_ID', '')

    # Нові окремі URLs + зворотня сумісність
    news_url  = env.get('PLANFIX_NEWS_URL')  or env.get('PLANFIX_BLOG_URL', '')
    cases_url = env.get('PLANFIX_CASES_URL') or env.get('PLANFIX_BLOG_URL', '')

    ids = load_db_ids()
    content_plan_db = ids.get('content_plan', '')

    cfg_errors = [k for k, v in [
        ('ANTHROPIC_API_KEY', api_key),
        ('NOTION_BLOG_TOKEN', blog_token),
        ('NOTION_BLOG_DB_ID', blog_db),
    ] if not v]
    if cfg_errors:
        print(f'[ERR] Не заповнено в .env: {", ".join(cfg_errors)}')
        return

    args = sys.argv[1:]

    # Режим: конкретна URL (тест)
    if args and args[0].startswith('http'):
        url = args[0]
        print(f'\n=== Тест одної статті ===\n{url}\n')
        process_article(url, api_key, blog_token, blog_db, main_token, content_plan_db)
        return

    # Визначити режим: --news / --tg / обидва (кейси прибрано — пишемо вручну)
    do_news = '--news' in args or not args
    do_tg   = '--tg'   in args or not args

    processed      = load_processed()
    existing_slugs = get_existing_slugs(blog_token, blog_db)
    print(f'Blog DB: вже {len(existing_slugs)} статей')

    total_done = total_skip = total_err = 0

    if do_news:
        if not news_url:
            print('[WARN] PLANFIX_NEWS_URL не заповнено в .env — пропускаю')
        else:
            d, s, e = run_source(
                news_url, 'Planfix.com — НОВИНИ',
                api_key, blog_token, blog_db, main_token, content_plan_db,
                processed, existing_slugs
            )
            total_done += d; total_skip += s; total_err += e

    if do_tg:
        tg_channel = env.get('PLANFIX_TG_CHANNEL', 'https://t.me/planfixua')
        # Парсимо публічний TG канал через t.me/s/
        tg_articles = scrape_tg_channel(tg_channel)
        new_tg = [a for a in tg_articles if a['url'] not in processed]
        if new_tg:
            print(f'\n=== @planfixua Telegram ({len(new_tg)} нових) ===')
            for i, art in enumerate(new_tg[:MAX_PER_RUN], 1):
                print(f'--- [{i}] {art["title"][:60]} ---')
                result = process_article(
                    art['url'], api_key, blog_token, blog_db,
                    main_token, content_plan_db, existing_slugs
                )
                processed.add(art['url'])
                save_processed(processed)
                if result == 'ok':     total_done += 1
                elif result == 'skip': total_skip += 1
                else:                  total_err  += 1
                time.sleep(3)
        else:
            print('\n=== @planfixua Telegram: нових постів немає ===')

    print(f'\n=== ПІДСУМОК: опубліковано {total_done}, пропущено {total_skip}, помилок {total_err} ===')

    # TG-звіт адміну після кожного запуску
    if tg_token and tg_admin and (total_done or total_err):
        mode = []
        if do_news:  mode.append('новини planfix.com')
        if do_cases: mode.append('кейси planfix.ru')
        lines = [f'🤖 <b>Planfix monitor</b> ({", ".join(mode)})']
        if total_done:
            lines.append(f'✅ Додано статей: <b>{total_done}</b> — перевір бота (/check)')
        if total_skip:
            lines.append(f'⏭ Пропущено: {total_skip}')
        if total_err:
            lines.append(f'❌ Помилок: {total_err}')
        if not total_done and not total_err:
            lines.append('ℹ️ Нових статей не знайдено')
        send_tg(tg_token, tg_admin, '\n'.join(lines))
        print('TG-звіт відправлено.')


if __name__ == '__main__':
    main()
