# Схема даних сайту crmcustoms.com

Документ описує джерела даних, поля Notion/API та правила видимості/SEO для розділів Blog та Cases.

---

## BLOG (сторінки `/blog`, `/blog/[slug]`)

### 1. Спосіб отримання даних статті

| Що | Джерело | Деталі |
|----|--------|--------|
| **Список статей** | n8n webhook GET | URL: `N8N_BLOG_LIST_URL` або `https://n8n.crmcustoms.com/webhook/ListPageBlog`. Параметри не передаються. |
| **Окрема стаття за slug** | Список + пошук по slug | Стаття з списку, де `property_link_name === slug` (slug з URL). |
| **Контент статті (тіло)** | n8n webhook GET | URL: `N8N_BLOG_PAGE_URL` або `https://n8n.crmcustoms.com/webhook/PageNotionBlog`. Параметр: **`?id={id}`** (id сторінки Notion). |

**Приклад:**
- Список: `GET https://n8n.crmcustoms.com/webhook/ListPageBlog`
- Контент: `GET https://n8n.crmcustoms.com/webhook/PageNotionBlog?id=abc-123-uuid`

---

### 2. SEO-теги та поля Notion

| Мета-тег / значення | Поле в даних (Notion/API) | Примітка |
|--------------------|---------------------------|----------|
| **`<title>`** | `article.name` або `article.title` | Fallback: «Блог». |
| **`<meta name="description">`** | `article.property_description` або `article.description` | Fallback: порожній рядок. |
| **`<meta property="og:image">`** | `article.property_2` | Масив з одним URL у `openGraph.images`. |
| **Canonical URL** | Не формується з поля | На рівні статті блогу canonical не задається; у кореневому layout є лише `metadataBase` і загальний `canonical: 'https://crmcustoms.com'`. |
| **Keywords** | На сторінці статті не виводяться | У `generateMetadata` для статті блогу окремого `keywords` немає. |
| **Robots** | Не задаються для статті | Використовується поведінка з кореневого layout. |

---

### 3. Видимість статті на сайті

| Де | Логіка на сайті |
|----|-----------------|
| **Список статей** | Фільтр по полю **на фронті немає**. Показуються всі записи, які повертає n8n (список). Видимість має регулюватися у n8n/Notion (які сторінки потрапляють у webhook). |
| **Окрема сторінка** | Відображається, якщо статтю знайдено в списку за `property_link_name === slug`. Якщо не знайдено — `notFound()`. |

Тобто перевірка «опубліковано/приховано» в коді сайту не використовується — лише наявність у відповіді API.

---

### 4. Тіло статті (контент)

- Джерело: **блоки Notion (page blocks)**, які повертає n8n endpoint контенту.
- Формат відповіді: масив об’єктів з полем `results` або `blocks` (масив блоків).
- Рендер: функція `renderNotionContent(blocks)` у `lib/blog.ts` перетворює блоки в HTML.

**Підтримувані типи блоків Notion:**

| Тип блоку | HTML |
|-----------|------|
| `heading_1`, `heading_2`, `heading_3` | `<h1>`, `<h2>`, `<h3>` |
| `paragraph` | `<p>` |
| `quote`, `callout` | `<blockquote>` |
| `bulleted_list_item`, `numbered_list_item` | `<ul>/<li>`, `<ol>/<li>` |
| `image` | `<img>` (url з `block.image.file.url` або `block.image.external.url`) |
| `video` | `<iframe>` (YouTube, Vimeo) або `<video>` |
| `embed` | `<iframe>` (SoundCloud, Spotify, CodePen, Figma, Twitter/X тощо) |

Окремого «текстового поля» для тіла статті в коді немає — лише блоки.

---

### 5. Сортування у списку блогу

| Призначення | Поле | Функція |
|-------------|------|--------|
| Сортування списку | `property_date` або `property_created_date` | `sortBlogPostsByDate()` — нові зверху (за датою по убыванню). |

---

### 6. Поле «Автори»

- На сторінці **списку блогу** автор відображається як **фіксований текст «CRMCUSTOMS»** і логотип (`/logo.svg`). Значення з Notion (relation або інше поле) **не використовуються**.
- На **сторінці окремої статті** блогу автор у UI не показується.

---

## CASES (сторінки `/cases`, `/cases/[slug]`)

### 7. Endpoint, SEO, видимість, тіло, сортування

#### Отримання даних

| Що | Джерело | Параметри |
|----|--------|-----------|
| **Список кейсів** | n8n GET | `N8N_CASES_LIST_URL` або `https://n8n.crmcustoms.com/webhook/list-page-cases`. Без параметрів. |
| **Окремий кейс за slug** | Список + пошук | Запис, де `property_slug === slug`. |
| **Контент кейсу** | n8n GET | `N8N_CASE_PAGE_URL` або `https://n8n.crmcustoms.com/webhook/get-page-cese`. Параметр: **`?id={id}`**. |

#### SEO-теги (Cases)

| Мета-тег / значення | Поле |
|---------------------|------|
| **`<title>`** | `property_name` (fallback: «Кейс») |
| **`<meta name="description">`** | `property_description` або `excerpt` |
| **`<meta property="og:image">`** | `article.image` або `article.background_photo` (fallback: `/placeholder.jpg`) |
| **Keywords** | `tags` + `keywords` (масиви) + `meta_keywords` (рядок, розбитий по комах). Всі об’єднуються в один рядок для `<meta name="keywords">`. |
| **Open Graph / Twitter** | title, description, type: article, publishedTime/modifiedTime, images |
| **JSON-LD** | Article з headline, image, datePublished, dateModified, description, keywords |
| **Canonical** | Для сторінки кейсу окремо не задається |

#### Видимість

- Як у блогу: **у коді сайту фільтрів немає**. У списку показуються всі кейси з відповіді API; окрема сторінка — якщо знайдено запис по `property_slug`.

#### Тіло статті

- Той самий механізм: блоки Notion з API контенту кейсу, рендер через `renderNotionContent()` (ті самі типи блоків).

#### Сортування

| Призначення | Поле | Функція |
|-------------|------|--------|
| Список кейсів | `property_format_date` або `property_date` | `sortArticlesByDate()` — нові зверху. |

---

## ЗАГАЛЬНЕ

### 8. Службові поля (formulas, rollups)

- У коді фронту **немає явних посилань** на типи полів Notion (formula, rollup тощо).
- Всі дані приходять як готові властивості об’єкта з n8n (наприклад `property_slug`, `property_name`). Якщо формула або rollup вже обчислені в n8n і віддаються в цих полях — їх можна не заповнювати через API; якщо n8n тягне сирі поля з Notion, то заповнювати треба ті поля, які очікує сайт (див. таблиці вище).

### 9. Порожні поля та fallback-значення

| Контекст | Fallback |
|----------|----------|
| Заголовок статті/кейсу | «Блог» / «Кейс» / «Без назви» (залежно від сторінки) |
| Опис (meta) | `''` або опис зі словника (для списків) |
| Зображення (обкладинка, og:image) | `[]` (блог), `/placeholder.jpg` (кейси), `/placeholder.svg` у списках |
| Контент статті | Порожній масив `[]` → порожній HTML |
| Slug відсутній | Стаття не потрапляє в `generateStaticParams` / не показується в списку посилань; окрема сторінка — notFound |
| ID відсутній | На сторінці статті показується повідомлення про помилку замість контенту |

**Приклади у коді:**
- `article.name || article.title || 'Блог'`
- `article.property_description || article.description || ''`
- `article.property_2 ? [article.property_2] : []` (og:image)
- Кейси: `article.property_name || 'Кейс'`, `article.image || article.background_photo || '/placeholder.jpg'`

---

## Короткі зведення полів

### Блог (основні поля з API)

| Поле | Призначення |
|------|-------------|
| `id` | Ідентифікатор для запиту контенту (`?id=`) |
| `property_link_name` | Slug у URL, ключ для пошуку статті |
| `name` / `title` | Заголовок, SEO title |
| `property_description` / `description` | Meta description |
| `property_2` | Зображення для og:image та обкладинки |
| `property_date`, `property_created_date` | Сортування списку |
| `property_categorytext` | Категорія (список блогу) |
| `property_photo1` | Запасне зображення |

### Кейси (основні поля з API)

| Поле | Призначення |
|------|-------------|
| `id` | Ідентифікатор для запиту контенту |
| `property_slug` | Slug у URL |
| `property_name` | Назва, SEO title |
| `property_description`, `property_meta_description`, `excerpt` | Опис, meta |
| `property_background_photo`, `property_social_network_img`, `property_image` | Зображення |
| `property_format_date`, `property_date` | Сортування, дати в SEO |
| `property_tags`, `property_services`, `property_category` | Теги, сервіси, категорії |
| `tags`, `keywords`, `meta_keywords` | SEO keywords |
| `property_last_edited_time` | lastModified у sitemap |

Файл створено за аналізом коду в `lib/blog.ts`, `app/[lang]/blog/`, `app/[lang]/cases/`, `components/blog/`, `app/sitemap.ts`, `app/layout.tsx`.
