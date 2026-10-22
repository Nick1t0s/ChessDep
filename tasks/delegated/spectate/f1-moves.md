# Цель
Фронтенд-модуль списка ходов партии `createMoveList` (используется на игровом экране и в повторе).

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
Создать: `frontend/js/game-moves.js`, `frontend/css/moves.css`. Больше ничего.

# Контракт и что сделать
Сигнатура — дословно контракт п. 8 (`createMoveList(container, { onSelect })` → `{ setEvents, appendEvents, lastSeq, select }`). Событие — объект из контракта п. 4.

Разметка внутри `container` (модуль сам делает `clear(container)` при создании):
- `div.mv-list` (прокручиваемый список).
- События `move` группируются в строки `div.mv-row` по номеру хода: номер = `Math.floor((ply - 1) / 2) + 1`; строка: `span.mv-num` («12.»), затем `span.mv-cell` белого хода и `span.mv-cell` чёрного (текст `payload.san`). Если первый ход строки — чёрный (возможно после депа), в белой ячейке «…».
- Событие `dep` — отдельная строка `div.mv-dep`: `«⚡ » + PIECE_NAME_RU[payload.from] + ' → ' + PIECE_NAME_RU[payload.to] + (payload.success ? ' ✓' : ' ✗')`, класс `ok` или `fail`.
- Прочие события (`resign`, `draw_offer`, `draw_accept`, `draw_decline`, `abort`, `flag`, `game_over`) — `div.mv-sys` (серый текст): `resign` «Сдача», `draw_offer` «Предложена ничья», `draw_accept` «Ничья принята», `draw_decline` «Ничья отклонена», `abort` «Партия отменена», `flag` «Время вышло», `game_over` — `'Итог: ' + (END_REASON_RU[payload.end_reason] ?? payload.end_reason)`.
- Каждая ячейка хода и каждая строка депа — кликабельна (`role: 'button'`, `tabindex: '0'`, `data-seq`), клик → `onSelect(event)`.
- `select(seq)`: снять класс `sel` со всех, добавить его элементу с `data-seq == seq` (если `seq !== null`).
- `setEvents` перерисовывает всё; `appendEvents` дописывает только события с `seq > lastSeq()`; после изменения список прокручивается вниз (`list.scrollTop = list.scrollHeight`).
- Импорты — только из `./dom.js` и `./format.js`.

`frontend/css/moves.css`, дословно:
```css
.mv-list { max-height: 320px; overflow-y: auto; font-family: var(--mono); font-size: 13px; display: flex; flex-direction: column; gap: 2px; }
.mv-row { display: grid; grid-template-columns: 38px 1fr 1fr; gap: 4px; align-items: center; }
.mv-num { color: var(--muted); }
.mv-cell, .mv-dep { padding: 3px 6px; border-radius: 6px; cursor: pointer; }
.mv-cell:hover, .mv-dep:hover { background: rgba(255,255,255,.06); }
.mv-cell.sel, .mv-dep.sel { background: color-mix(in srgb, var(--gold) 25%, transparent); color: var(--text); }
.mv-dep { font-size: 12px; margin-left: 38px; }
.mv-dep.ok { color: #4ade80; }
.mv-dep.fail { color: #ff5470; }
.mv-sys { color: var(--muted); font-size: 12px; margin-left: 38px; padding: 2px 6px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
