# Цель
В профиле в таблице партий — ссылка на соперника и на повтор партии.

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
Менять: только `frontend/js/profile.js`.

# Контракт и что сделать
В таблице «Партии»:
- ячейка «Соперник» — вместо текста ссылка `h('a', { href: '/user.html?login=' + encodeURIComponent(game.opponent_login) }, game.opponent_login)`;
- добавить последнюю колонку: заголовок «Повтор», в строке `h('a', { href: '/replay.html?id=' + game.id, class: 'btn btn-ghost btn-sm' }, 'Повтор')`;
- если в таблице есть строка-заглушка «Партий ещё не было» с `colspan` — увеличить `colspan` на 1 (если `colspan` задаётся атрибутом, которого нет в списке разрешённых у `h()`, — задать через `td.colSpan = N`).

Больше ничего в файле не менять.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
