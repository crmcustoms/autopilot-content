# -*- coding: utf-8 -*-
"""
Generyuye vidformatovani posty cherez Claude API i stavyt status 'Na zatverdzhenni'.
Bot vidpravyt yikh adminu na skhvalennya.
Zapusk: python scripts/generate_posts.py
"""
import io, sys, json, os, urllib.request, urllib.error, time
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

def claude(api_key, prompt):
    body = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 1024,
        'messages': [{'role': 'user', 'content': prompt}],
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages', data=body,
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data['content'][0]['text']

def notion_create(token, db_id, props):
    body = json.dumps({'parent': {'database_id': db_id}, 'properties': props},
                      ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request('https://api.notion.com/v1/pages', data=body, headers={
        'Authorization': 'Bearer ' + token,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"

def rt(text):
    # Ріжемо на чанки по 2000 символів (ліміт Notion rich_text блоку)
    chunks = []
    for i in range(0, len(str(text)), 2000):
        chunks.append({'type': 'text', 'text': {'content': str(text)[i:i+2000]}})
    return chunks

# Промпт для генерації Telegram-поста (з TZ v2.2)
TG_PROMPT = """Ти — Максим, власник CRMCUSTOMS, 10+ років автоматизації в Україні.
Голос каналу @prodayslonakume («Продай слона | Про бізнес українською»).
ЦА: власники бізнесу 35-55 років, Україна.

Напиши пост для Telegram на тему: {TOPIC}

Структура:
— перший рядок: emoji + заголовок-хук (без крапки, до 12 слів)
— порожній рядок
— тіло: 3-4 коротких абзаци, кожен 2-3 речення. Конкретно, без води.
— порожній рядок
— порада або інсайт одним рядком (можна з emoji)
— порожній рядок
— CTA: одне просте запитання або заклик (без «підписуйтесь»)

Правила:
— тільки українська мова
— жодних RU-сервісів (Bitrix24, AmoCRM, 1С)
— реальні цифри якщо є
— 150-220 слів
— звертання на «ти»
— Telegram Markdown: *жирний* для ключових слів, без інших тегів

Виведи ТІЛЬКИ текст поста, без пояснень."""

TOPICS = [
    {
        'topic': 'Чому менеджери не користуються CRM — і що з цим робити',
        'name': 'Чому менеджери не користуються CRM',
        'type': 'Піст',
        'platforms': ['Telegram'],
    },
    {
        'topic': '3 питання які власник бізнесу має задати собі перед впровадженням CRM',
        'name': '3 питання перед впровадженням CRM',
        'type': 'Піст',
        'platforms': ['Telegram'],
    },
    {
        'topic': 'Як автоматизація допомогла компанії скоротити час на обробку замовлення з 40 хвилин до 7',
        'name': 'Кейс: скорочення часу обробки замовлень у 6 разів',
        'type': 'Кейс',
        'platforms': ['Telegram'],
    },
]

def main():
    env = load_env()
    api_key = env.get('ANTHROPIC_API_KEY', '')
    notion_token = env.get('NOTION_TOKEN', '')
    ids = load_db_ids()

    if not api_key:
        print('[ERR] ANTHROPIC_API_KEY vidsutni'); return
    if not notion_token:
        print('[ERR] NOTION_TOKEN vidsutni'); return

    print()
    print('Generyuyu posty cherez Claude API...')
    print()

    created = 0
    for i, item in enumerate(TOPICS, 1):
        print(f'[{i}/{len(TOPICS)}] {item["name"]}')
        print('  Generyuyu...')

        prompt = TG_PROMPT.replace('{TOPIC}', item['topic'])
        try:
            text = claude(api_key, prompt)
        except Exception as e:
            print(f'  ERR Claude: {e}')
            continue

        # Перший рядок — заголовок
        first_line = text.strip().split('\n')[0].strip()
        title = first_line[:100] if first_line else item['name']

        props = {
            'Назва': {'title': [{'type': 'text', 'text': {'content': title}}]},
            'Текст посту': {'rich_text': rt(text)},
            'Статус': {'select': {'name': 'На затвердженні'}},
            'Тип': {'select': {'name': item['type']}},
            'Платформи': {'multi_select': [{'name': p} for p in item['platforms']]},
        }
        _, err = notion_create(notion_token, ids['content_plan'], props)
        if err:
            print(f'  ERR Notion: {err}')
            continue

        print(f'  OK -> Notion (status: Na zatverdzhenni)')
        print(f'  Poperednii perehlyad:')
        print()
        # Показати перші 300 символів посту
        preview = text.strip()[:300]
        for line in preview.split('\n'):
            print(f'    {line}')
        print('    ...')
        print()
        created += 1
        time.sleep(1)  # не спамити API

    print(f'Stvoreno: {created}/{len(TOPICS)} postiv zi statusom "Na zatverdzhenni"')
    print()
    print('Nastupni kroky:')
    print('  1. Zapusty start_bot.bat')
    print('  2. Bot vidpravyt posty tobi v Telegram na skhvalennya')
    print('  3. Natyskay [Opublikuvaty v TG] -> post ide v kanal @prodayslonakume')

if __name__ == '__main__':
    main()
