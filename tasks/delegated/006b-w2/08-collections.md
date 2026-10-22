# Цель
Публичные страницы коллекций: список коллекций и страница одной коллекции со скинами, сгруппированными по редкости.

# Контекст
Прочитай сначала (это образцы, им надо следовать):
- `frontend/index.html` и `frontend/js/index.js` — образец страницы: HTML-каркас, `initLayout`, создание `main` через `h()`.
- `frontend/js/dom.js` — `h(tag, attrs, ...children)`, `clear(el)`. DOM создаётся ТОЛЬКО через `h()` и `textContent`. Разрешённые атрибуты `h()`: class, id, type, disabled, title, href (только относительный `/...` или `#...`), value, name, role, tabindex, for, required, readonly, maxlength, minlength, autocomplete, placeholder, hidden, min, max, step, rows, checked, aria-*, data-*, onClick/onInput/onChange/onSubmit/onKeydown.
- `frontend/js/api.js` — `api(method, path, body)`; путь без `/api/v1`, например `api('GET', '/inventory')`. При ошибке бросает `ApiError` с полями `status`, `code`, `message` (сообщение уже по-русски).
- `frontend/js/layout.js` — `initLayout({ auth, active })` возвращает `me` (`{id, login, role, balance, elo, daily_bonus_available_at}`) или `null`; `setBalance(n)`.
- `frontend/js/toast.js` — `toast(message, kind)`, kind: `info` | `success` | `error`.
- `frontend/js/modal.js` — `openModal({ title, titleAnim: 'none', body, actions, dismissible })` возвращает функцию закрытия; `actions` — `[{ label, kind: 'gold'|'ghost'|'danger', onClick }]`, модалка закрывается после `onClick`, если он не вернул `false`. `confirmModal(title, text, okLabel, kind) → Promise<boolean>`.
- `frontend/js/format.js` — `fmtCrystals(n)`, `PIECE_NAME_RU`, `END_REASON_RU`.
- `frontend/js/items.js` — `itemCard(def, { exterior, badge, extra, selected, onClick })`, `skinPreview(def)`, `RARITIES`, `RARITY_RU`, `EXTERIOR_RU`, `SLOT_RU`. Стили — `frontend/css/items.css` (классы `.item-grid`, `.item-card`).
- Готовые CSS-классы: `.wrap-wide` (контейнер страницы), `.card`, `.card-title`, `.btn`, `.btn-gold`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.field` (обёртка `label` + `input`), `.mono`, `.pill`, `.page-title`.

Общие правила для всех страниц:
- HTML-файл страницы — копия каркаса `frontend/index.html`: свой `<title>`, подключить `css/base.css`, `css/layout.css`, `css/components.css`, `css/items.css` и свой CSS-файл, ровно один `<script type="module" src="js/<страница>.js"></script>`, пустой `<body></body>`.
- Модуль страницы начинается с `const me = await initLayout({...})`, затем создаёт `const main = h('main', { class: 'wrap-wide <имя-страницы>' })` и `document.body.appendChild(main)`.
- Любой запрос — через `api()`. Ошибку показывать `toast(e.message, 'error')`.
- Даты: `new Date(iso).toLocaleString('ru-RU')`. Деньги: `fmtCrystals(n)`.
- Пользовательский текст (логины, записки, названия) вставлять только как дочерние строки `h()` или через `textContent`.

# Область
Создать: `frontend/collections.html`, `frontend/collection.html`, `frontend/js/collections.js`, `frontend/js/collection.js`, `frontend/css/collections.css`.

# Контракт
### collections.html
`initLayout({ auth: 'optional', active: '' })`, main `wrap-wide collections`, `<title>Коллекции — ChessDep</title>`.
- `GET /collections` → `[{code, name, description, status: 'released'|'retired', released_at, items_count}]`.
- `h1.page-title` «Коллекции»; сетка `div.col-grid`. Для каждой — `div.card.col-card`:
  - `h3.card-title` (name);
  - `span.pill` со статусом: «В продаже» для `released`, «Снята с выпуска» для `retired`;
  - `p.col-desc` (description);
  - `p.col-meta`: «Скинов: N · выпущена <дата released_at>»;
  - ссылка `h('a', { href: '/collection.html?code=' + code, class: 'btn btn-gold btn-sm' }, 'Смотреть')`.

### collection.html
`initLayout({ auth: 'optional', active: '' })`, main `wrap-wide collection`, `<title>Коллекция — ChessDep</title>`.
- `code` из `?code=`; не `/^[a-z0-9-]{2,40}$/` → `p` «Некорректная ссылка».
- `GET /collections/<code>` → `{code, name, description, status, released_at, items: def[]}`.
- `h1.page-title` (name), `p.col-desc` (description). Затем по редкостям в порядке от редкой к обычной: `[...RARITIES].reverse()`. Для каждой редкости, у которой есть скины: `h2.col-rarity.r-<rarity>` с текстом `RARITY_RU[rarity]`, затем `div.item-grid` из `itemCard(def, { extra: h('a', { href: '/market-item.html?def=' + def.id, class: 'btn btn-ghost btn-sm' }, 'На маркете') })`.

`frontend/css/collections.css`, дословно:
```css
.col-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.col-card { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.col-desc { color: var(--muted); font-size: 13.5px; }
.col-meta { color: var(--muted); font-size: 12.5px; }
.col-rarity { margin: 18px 0 10px; font-size: 16px; color: var(--rarity, var(--text)); }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
