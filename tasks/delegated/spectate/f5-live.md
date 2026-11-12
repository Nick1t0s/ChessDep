# Цель
Страница «Смотреть»: список идущих партий со ссылкой на просмотр.

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
Создать: `frontend/live.html`, `frontend/js/live.js`, `frontend/css/live.css`.

# Контракт и что сделать
- `initLayout({ auth: 'required', active: 'live' })`, main `wrap-wide live`, `<title>Смотреть — ChessDep</title>`.
- `h1.page-title` «Идут партии», `p.lv-hint` «Обновляется каждые 10 секунд».
- `GET /games/live?limit=50` (контракт п. 3) → сетка `div.lv-grid`, для каждой партии `div.card.lv-card`:
  - `div.lv-players`: `b` (white.login) + `span.lv-elo` («(1216)») + `span.lv-vs` «vs» + `b` (black.login) + `span.lv-elo`;
  - `p.lv-meta`: `time_control + ' · ход ' + (Math.floor(ply / 2) + 1) + ' · депов ' + deps_used`;
  - ссылка `h('a', { href: '/game.html?id=' + id, class: 'btn btn-gold btn-sm' }, 'Смотреть')`.
- Пусто → `p.lv-empty` «Сейчас никто не играет.» и ссылка `h('a', { href: '/index.html', class: 'btn btn-ghost btn-sm' }, 'Сыграть')`.
- Перезагрузка списка каждые 10 000 мс (`setInterval`), ошибки — `toast` не чаще одного раза подряд (флаг).

`frontend/css/live.css`, дословно:
```css
.lv-hint { color: var(--muted); font-size: 13px; margin-bottom: 12px; }
.lv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.lv-card { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.lv-players { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.lv-elo { color: var(--muted); font-size: 12px; font-family: var(--mono); }
.lv-vs { color: var(--gold); font-weight: 800; margin: 0 4px; }
.lv-meta { color: var(--muted); font-size: 13px; }
.lv-empty { color: var(--muted); margin-bottom: 8px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
