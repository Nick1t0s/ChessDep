# Цель
Страница повтора партии по событиям: доска, навигация по ходам, список ходов, итог, чат только для чтения.

# Контекст
Прочитай сначала:
- `docs/contracts-spectate.md` — контракт API и модулей; поля и сигнатуры — дословно оттуда.
- `frontend/js/dom.js` — `h(tag, attrs, ...children)`, `clear(el)`. DOM ТОЛЬКО через `h()` и `textContent`. Атрибуты `h()`: class, id, type, disabled, title, href (только `/...` или `#...`), value, name, role, tabindex, for, required, readonly, maxlength, minlength, autocomplete, placeholder, hidden, min, max, step, rows, checked, aria-*, data-*, onClick/onInput/onChange/onSubmit/onKeydown. Вместо атрибутов можно передать `null` или `{}`.
- `frontend/js/api.js` — `api(method, path, body)`; путь без `/api/v1`. Ошибка — `ApiError` с `status`, `code`, `message` (по-русски).
- `frontend/js/layout.js` — `initLayout({ auth, active })` → `me | null`. `frontend/js/toast.js` — `toast(msg, 'info'|'success'|'error')`. `frontend/js/modal.js` — `openModal`, `confirmModal`. `frontend/js/format.js` — `fmtCrystals`, `fmtClock`, `PIECE_NAME_RU`, `END_REASON_RU`.
- `frontend/js/board.js` — `createBoard(container, { onSquareClick })` → `{ render(state, opts), setOrientation(color), squareEl(sq), element }`; `render` принимает объект с полями `board`, `players`, `you`, `last_action`, `check_square` (см. файл).
- Образец страницы: `frontend/index.html` + `frontend/js/index.js`. Готовые классы: `.wrap-wide`, `.card`, `.card-title`, `.btn`, `.btn-gold`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.mono`, `.pill`, `.page-title`.

Правила страниц: HTML — копия каркаса `frontend/index.html` (свой `<title>`, CSS `css/base.css`, `css/layout.css`, `css/components.css` + свои, ровно один `<script type="module">`, пустой `<body>`). Даты — `new Date(iso).toLocaleString('ru-RU')`. Ошибки API — `toast(e.message, 'error')`. Пользовательский текст (логины, сообщения чата) — только как текст.
Модули `frontend/js/game-moves.js` и `frontend/js/game-chat.js` пишут другие исполнители параллельно — не создавать, импортировать по контракту п. 8.

# Область
Создать: `frontend/replay.html`, `frontend/js/replay.js`, `frontend/css/replay.css`. `replay.html` подключает также `css/board.css`, `css/moves.css`, `css/chat.css`.

# Контракт и что сделать
- `initLayout({ auth: 'required', active: '' })`, main `wrap-wide replay`, `<title>Повтор партии — ChessDep</title>`.
- `id` из `?id=` (регэксп uuid `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`), иначе `p` «Некорректная ссылка».
- `GET /games/<id>/events` → `{ game, events }` (контракт п. 4).
- Позиции: массив `positions` — сначала начальная `{ board: game.initial_board, check_square: null, last_action: null, ev: null }`, затем по одной на каждое событие `move` и `dep` (в порядке `seq`): `{ board: ev.board, check_square: ev.check_square, last_action: { kind: ev.kind, ...ev.payload }, ev }`. Текущий индекс `idx` (стартовое значение — последний).
- Разметка `div.rp-layout` (две колонки):
  - слева: `div.rp-head` (`white.login (elo)` vs `black.login (elo)`, `time_control`, итог: `result` → «Победили белые» / «Победили чёрные» / «Ничья» / «Партия идёт» для `status === 'active'`, плюс `END_REASON_RU[end_reason]`); контейнер доски `createBoard`; `div.rp-controls` с кнопками ⏮ ◀ ▶ ⏭ (`btn btn-ghost btn-sm`, `aria-label` «В начало» / «Назад» / «Вперёд» / «В конец») и кнопкой «Перевернуть»; `p.rp-info` — для текущей позиции: номер хода, а для депа — `'Деп: ' + PIECE_NAME_RU[from] + ' → ' + PIECE_NAME_RU[to] + ' · шанс ' + (chance * 100).toFixed(2) + '% · ' + (success ? 'успех' : 'провал')`;
  - справа: карточка «Ходы» с `createMoveList(box, { onSelect: (ev) => go(index позиции с этим ev.seq) })`, `setEvents(events)`; карточка «Чат» с `createChat(box, { gameId: id, canWrite: false })` и `load()`.
- `go(i)`: ограничить `0..positions.length-1`; `idx = i`; `board.render({ board, check_square, last_action, you: orientation, players: { white: { loadout: game.white_loadout }, black: { loadout: game.black_loadout } } }, {})`; `moves.select(positions[idx].ev?.seq ?? null)`; обновить `rp-info`.
- Ориентация `orientation`: `'white'` по умолчанию; «Перевернуть» меняет и вызывает `board.setOrientation(orientation)` + `go(idx)`.
- Клавиатура: `ArrowLeft` / `ArrowRight` / `Home` / `End` на `document` → навигация.

`frontend/css/replay.css`, дословно:
```css
.rp-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 16px; align-items: start; }
@media (max-width: 900px) { .rp-layout { grid-template-columns: 1fr; } }
.rp-head { margin-bottom: 10px; font-size: 14px; }
.rp-head b { color: var(--text); }
.rp-controls { display: flex; gap: 6px; justify-content: center; margin-top: 10px; flex-wrap: wrap; }
.rp-info { text-align: center; color: var(--muted); font-size: 13px; margin-top: 8px; min-height: 18px; }
.replay .card { margin-bottom: 14px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
