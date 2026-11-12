# Цель
Публичная страница игрока: Elo, статистика и список партий со ссылками на повтор.

# Контекст
Прочитай сначала:
- `docs/contracts-spectate.md` — контракт API и модулей; поля и сигнатуры — дословно оттуда.
- `frontend/js/dom.js` — `h(tag, attrs, ...children)`, `clear(el)`. DOM ТОЛЬКО через `h()` и `textContent`. Атрибуты `h()`: class, id, type, disabled, title, href (только `/...` или `#...`), value, name, role, tabindex, for, required, readonly, maxlength, minlength, autocomplete, placeholder, hidden, min, max, step, rows, checked, aria-*, data-*, onClick/onInput/onChange/onSubmit/onKeydown. Вместо атрибутов можно передать `null` или `{}`.
- `frontend/js/api.js` — `api(method, path, body)`; путь без `/api/v1`. Ошибка — `ApiError` с `status`, `code`, `message` (по-русски).
- `frontend/js/layout.js` — `initLayout({ auth, active })` → `me | null`. `frontend/js/toast.js` — `toast(msg, 'info'|'success'|'error')`. `frontend/js/modal.js` — `openModal`, `confirmModal`. `frontend/js/format.js` — `fmtCrystals`, `fmtClock`, `PIECE_NAME_RU`, `END_REASON_RU`.
- `frontend/js/board.js` — `createBoard(container, { onSquareClick })` → `{ render(state, opts), setOrientation(color), squareEl(sq), element }`; `render` принимает объект с полями `board`, `players`, `you`, `last_action`, `check_square` (см. файл).
- Образец страницы: `frontend/index.html` + `frontend/js/index.js`. Готовые классы: `.wrap-wide`, `.card`, `.card-title`, `.btn`, `.btn-gold`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.mono`, `.pill`, `.page-title`.

Правила страниц: HTML — копия каркаса `frontend/index.html` (свой `<title>`, CSS `css/base.css`, `css/layout.css`, `css/components.css` + свои, ровно один `<script type="module">`, пустой `<body>`). Даты — `new Date(iso).toLocaleString('ru-RU')`. Ошибки API — `toast(e.message, 'error')`. Пользовательский текст (логины, сообщения чата) — только как текст.

# Область
Создать: `frontend/user.html`, `frontend/js/user.js`, `frontend/css/user.css`.

# Контракт и что сделать
- `initLayout({ auth: 'required', active: '' })`, main `wrap-wide user`, `<title>Игрок — ChessDep</title>`.
- `login` из `?login=`; не `/^[A-Za-z0-9_-]{3,16}$/` → `p` «Некорректная ссылка».
- `GET /users/<login>` (контракт п. 5) → `h1.page-title` (login); `div.card` со строками `p.us-row` (`span` подпись + `b` значение): Elo, Сыграно, Победы, Ничьи, Поражения, На сайте с (дата `created_at`).
- `GET /users/<login>/games?limit=20` (+ `&before=` + `encodeURIComponent(next_before)` для «Ещё») → карточка «Партии», `table.us-table` с колонками Дата (`finished_at`), Соперник (ссылка `'/user.html?login=' + encodeURIComponent(opponent_login)`), Цвет («Белые» / «Чёрные»), Результат (`null` → «Отменена», `'draw'` → «Ничья», `=== color` → «Победа», иначе «Поражение»), Причина (`END_REASON_RU`), Контроль, Elo (`null` → «—», иначе со знаком), и ссылка `h('a', { href: '/replay.html?id=' + id, class: 'btn btn-ghost btn-sm' }, 'Повтор')`. Кнопка «Ещё», пока `next_before !== null`. Пусто → строка «Партий ещё нет».
- 404 → `p` «Игрок не найден».
- Таблицу обернуть в `div.table-wrap`.

`frontend/css/user.css`, дословно:
```css
.user .card { margin-bottom: 16px; }
.us-row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.us-row span { color: var(--muted); }
.us-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.us-table th, .us-table td { padding: 7px 8px; border-bottom: 1px solid var(--line); text-align: left; }
.us-table th { color: var(--muted); font-weight: 600; }
.us-table a:not(.btn) { color: var(--gold); }
.user .table-wrap { overflow-x: auto; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
