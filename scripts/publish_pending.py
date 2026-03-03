# -*- coding: utf-8 -*-
"""
Bere vsi posty zi statusom 'Na zatverdzhenni' z Notion
i publikuye yikh v Telegram kanal.
Pislya publikatsiyi status -> 'Opublikovano'.
Zapusk: python scripts/publish_pending.py
"""
import io, sys, json, os, urllib.request, urllib.error
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    with open(os.path.join(ROOT, '.env'), encoding='utf-8') as f:
        env = {}
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        return env

def load_db_ids():
    with open(os.path.join(ROOT, 'NOTION_DATABASE_IDS.json'), encoding='utf-8') as f:
        return json.load(f)

def notion_req(token, method, path, body=None):
    url = 'https://api.notion.com/v1' + path
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': 'Bearer ' + token,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

def tg_send(token, channel, text):
    body = json.dumps({'chat_id': channel, 'text': text[:4096]}).encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=body, headers={'Content-Type': 'application/json'}, method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

def get_plain(prop, key='title'):
    return ''.join(t.get('plain_text', '') for t in prop.get(key, []) if isinstance(t, dict))

def main():
    env = load_env()
    notion_token = env['NOTION_TOKEN']
    tg_token = env['TELEGRAM_BOT_TOKEN']
    channel = env.get('TELEGRAM_CHANNEL_ID', '@prodayslonakume')
    ids = load_db_ids()

    # Отримати всі пости "На затвердженні"
    data, err = notion_req(notion_token, 'POST', f'/databases/{ids["content_plan"]}/query', {
        'filter': {'property': 'Статус', 'select': {'equals': 'На затвердженні'}},
        'page_size': 20,
    })
    if err:
        print(f'Notion ERR: {err}'); return

    pages = data.get('results', [])
    print(f'Znayshlo postiv "Na zatverdzhenni": {len(pages)}')
    if not pages:
        print('Nemaye postiv dlya publikatsiyi.')
        return

    published = 0
    for page in pages:
        props = page.get('properties', {})
        name = get_plain(props.get('Назва', {}), 'title')
        text = get_plain(props.get('Текст посту', {}), 'rich_text')
        page_id = page['id']

        content = text if text.strip() else name
        if not content.strip():
            print(f'  SKIP (porozhniy): {name[:40]}')
            continue

        print(f'  Publikuyu: {name[:50]}...')
        result, err = tg_send(tg_token, channel, content)
        if err:
            print(f'  TG ERR: {err}')
            continue

        # Оновити статус в Notion
        notion_req(notion_token, 'PATCH', f'/pages/{page_id}', {
            'properties': {'Статус': {'select': {'name': 'Опубліковано'}}}
        })

        msg_id = result.get('result', {}).get('message_id', '?')
        print(f'  OK -> message_id={msg_id}')
        published += 1

    print()
    print(f'Opublikovano: {published}/{len(pages)}')
    print(f'Perevirte kanal {channel}')

if __name__ == '__main__':
    main()
