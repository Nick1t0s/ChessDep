# Цель
Две небольшие страницы: подарки (входящие и отправленные) и лидерборд.

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
Создать: `frontend/gifts.html`, `frontend/js/gifts.js`, `frontend/leaderboard.html`, `frontend/js/leaderboard.js`, `frontend/css/social.css`. Оба HTML подключают `css/social.css`.

# Контракт
### gifts.html
`initLayout({ auth: 'required', active: '' })`, main `wrap-wide gifts`, `<title>Подарки — ChessDep</title>`.
- `GET /me/gifts?direction=<in|out>&limit=20` и следующая страница `&before_id=<next_cursor>` → `{items: [{id, item: {id, def, wear, exterior}, from_login, to_login, note: string|null, seen: boolean, created_at}], next_cursor: number|null}`.
- `h1.page-title` «Подарки»; вкладки `div.sc-tabs`: «Входящие» (`in`, по умолчанию) и «Отправленные» (`out`), активная `btn-gold`, неактивная `btn-ghost`; `p.sc-hint`: «Подарить предмет можно из » + `h('a', { href: '/inventory.html' }, 'инвентаря')`.
- `div.item-grid` из `itemCard(g.item.def, { exterior: g.item.exterior, badge: (dir === 'in' && !g.seen) ? 'Новый' : undefined, extra })`, где `extra` = `div.sc-gift`:
  - `p.sc-who`: «От <from_login>» для `in` или «Кому: <to_login>» для `out`;
  - `p.sc-date` (дата);
  - если `note` — `p.sc-note` (`note` как текст).
- Кнопка «Ещё» (`btn btn-ghost btn-sm`), пока `next_cursor !== null`. Пусто → `p` «Подарков нет».

### leaderboard.html
`initLayout({ auth: 'optional', active: 'leaderboard' })`, main `wrap-wide leaderboard`, `<title>Лидеры — ChessDep</title>`.
- `GET /leaderboard?by=<elo|balance>&limit=100` → `[{rank, login, elo, balance}]`.
- `h1.page-title` «Лидеры»; вкладки `div.sc-tabs`: «По Elo» (по умолчанию), «По балансу».
- `table.sc-table` с колонками #, Игрок, Elo, Баланс (`fmtCrystals`). Строке с `login === me?.login` добавить класс `me`.

`frontend/css/social.css`, дословно:
```css
.sc-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.sc-hint { color: var(--muted); font-size: 13px; margin-bottom: 12px; }
.sc-hint a { color: var(--gold); }
.sc-gift p { margin: 2px 0; font-size: 12.5px; }
.sc-who { font-weight: 600; }
.sc-date { color: var(--muted); }
.sc-note { font-style: italic; color: var(--text); word-break: break-word; }
.sc-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.sc-table th, .sc-table td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; }
.sc-table th { color: var(--muted); font-weight: 600; }
.sc-table tr.me td { color: var(--gold); font-weight: 700; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
