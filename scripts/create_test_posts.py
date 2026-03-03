# -*- coding: utf-8 -*-
"""
Stvoryuye 3 testovi posty v Notion zi statusom 'Na zatverdzhenni'.
Bot vidpravyt yikh tobi na skhvalennya pry nastupnomu /check abo pry zapuski.
Zapusk: python scripts/create_test_posts.py
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

def notion_post(token, path, body):
    url = 'https://api.notion.com/v1' + path
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': 'Bearer ' + token,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)

def rt(text):
    return [{'type': 'text', 'text': {'content': str(text)[:2000]}}]

TEST_POSTS = [
    {
        'name': 'Чому CRM не приживається в малому бізнесі',
        'text': (
            'Впровадили CRM — і нікому. Знайома ситуація?\n\n'
            'Я бачу це постійно: власник платить за Planfix або інший інструмент, '
            'менеджери відкривають його раз на тиждень щоб закрити вкладку.\n\n'
            'Причина не в команді. Причина в тому, що систему налаштували під процес '
            '"як має бути", а не "як є насправді".\n\n'
            'Перше що я роблю на аудиті — питаю менеджера: "Покажи як ти зараз '
            'працюєш". Не як треба. Як є.\n\n'
            'Потім система будується навколо цього — і люди в ній залишаються.\n\n'
            'Хочеш аудит свого процесу? Пиши в особисті.'
        ),
        'platforms': ['Telegram'],
        'type': 'Піст',
    },
    {
        'name': '3 ознаки що ваш відділ продажів працює без системи',
        'text': (
            '3 ознаки що відділ продажів працює "на пам\'яті", а не в системі:\n\n'
            '1. Менеджер йде у відпустку — і частина клієнтів зникає разом з ним\n'
            '2. Ви не можете сказати скільки лідів прийшло за минулий тиждень без '
            'того щоб дзвонити кожному менеджеру\n'
            '3. "Він обіцяв передзвонити" — це все що ви знаєте про статус угоди\n\n'
            'Якщо хоча б один пункт про вас — це не проблема команди.\n'
            'Це відсутність процесу.\n\n'
            'Можна виправити за 2 тижні. Перевірено.'
        ),
        'platforms': ['Telegram', 'LinkedIn'],
        'type': 'Піст',
    },
    {
        'name': 'Кейс: автоматизація відділу продажів за 14 днів',
        'text': (
            'Клієнт: компанія 12 осіб, будматеріали, Київ.\n'
            'Ситуація: 3 менеджери, Excel, месенджери, забуті дзвінки.\n\n'
            'Тиждень 1:\n'
            '— Налаштували Planfix під реальний процес менеджерів\n'
            '— Підключили вхідні з сайту і Telegram\n'
            '— Автонагадування по кожній угоді\n\n'
            'Тиждень 2:\n'
            '— Інтеграція з 1С (залишки, ціни — в картці клієнта)\n'
            '— Дашборд для власника: конверсія, середній чек, воронка\n\n'
            'Результат через місяць:\n'
            '+ 23% до конверсії (менше втрачених лідів)\n'
            '- 40% часу менеджера на рутину\n\n'
            'Що там складного.'
        ),
        'platforms': ['Telegram', 'LinkedIn', 'Facebook'],
        'type': 'Кейс',
    },
]

def main():
    env = load_env()
    token = env.get('NOTION_TOKEN')
    ids = load_db_ids()
    db_id = ids['content_plan']

    print()
    print('Stvoryu 3 testovi posty v Notion (status: Na zatverdzhenni)...')
    print()

    for i, post in enumerate(TEST_POSTS, 1):
        props = {
            'Назва': {'title': rt(post['name'])},
            'Текст посту': {'rich_text': rt(post['text'])},
            'Статус': {'select': {'name': 'На затвердженні'}},
            'Тип': {'select': {'name': post['type']}},
            'Платформи': {'multi_select': [{'name': p} for p in post['platforms']]},
        }
        _, err = notion_post(token, '/pages', {'parent': {'database_id': db_id}, 'properties': props})
        if err:
            print(f'  [{i}] ERR: {err}')
        else:
            print(f'  [{i}] OK: {post["name"][:50]}')

    print()
    print('Hotovo!')
    print()
    print('Nastupni kroky:')
    print('  1. Dodaj @crmcontent_bot yak admina kanalu @prodayslonakume')
    print('  2. Zapusty bota: start_bot.bat')
    print('  3. Bot vidpravyt tobi 3 posty na skhvalennya')
    print('  4. Natyskay [Opublikuvaty v TG] — post ide v kanal')

if __name__ == '__main__':
    main()
