# Цель
Игровой экран: режим зрителя, панель ходов с просмотром любой позиции, чат.

# Контекст
Прочитай сначала:
- `docs/contracts-spectate.md` — контракт API и модулей; поля и сигнатуры — дословно оттуда.
- `frontend/js/dom.js` — `h(tag, attrs, ...children)`, `clear(el)`. DOM ТОЛЬКО через `h()` и `textContent`. Атрибуты `h()`: class, id, type, disabled, title, href (только `/...` или `#...`), value, name, role, tabindex, for, required, readonly, maxlength, minlength, autocomplete, placeholder, hidden, min, max, step, rows, checked, aria-*, data-*, onClick/onInput/onChange/onSubmit/onKeydown. Вместо атрибутов можно передать `null` или `{}`.
- `frontend/js/api.js` — `api(method, path, body)`; путь без `/api/v1`. Ошибка — `ApiError` с `status`, `code`, `message` (по-русски).
- `frontend/js/layout.js` — `initLayout({ auth, active })` → `me | null`. `frontend/js/toast.js` — `toast(msg, 'info'|'success'|'error')`. `frontend/js/modal.js` — `openModal`, `confirmModal`. `frontend/js/format.js` — `fmtCrystals`, `fmtClock`, `PIECE_NAME_RU`, `END_REASON_RU`.
- `frontend/js/board.js` — `createBoard(container, { onSquareClick })` → `{ render(state, opts), setOrientation(color), squareEl(sq), element }`; `render` принимает объект с полями `board`, `players`, `you`, `last_action`, `check_square` (см. файл).
- Образец страницы: `frontend/index.html` + `frontend/js/index.js`. Готовые классы: `.wrap-wide`, `.card`, `.card-title`, `.btn`, `.btn-gold`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.mono`, `.pill`, `.page-title`.

Правила страниц: HTML — копия каркаса `frontend/index.html` (свой `<title>`, CSS `css/base.css`, `css/layout.css`, `css/components.css` + свои, ровно один `<script type="module">`, пустой `<body>`). Даты — `new Date(iso).toLocaleString('ru-RU')`. Ошибки API — `toast(e.message, 'error')`. Пользовательский текст (логины, сообщения чата) — только как текст.
Дополнительно прочитай целиком `frontend/js/game.js` и `frontend/game.html` — их ты меняешь. Модули `frontend/js/game-moves.js` и `frontend/js/game-chat.js` пишут ДРУГИЕ исполнители параллельно: их не создавать, а импортировать по контракту п. 8.

# Область
Менять: `frontend/js/game.js`, `frontend/game.html` (только добавить `<link rel="stylesheet" href="css/moves.css">` и `<link rel="stylesheet" href="css/chat.css">`), `frontend/css/game.css` (только дописать правила из п. 6 в конец).

# Контракт и что сделать
1. **Импорты:** `import { createMoveList } from './game-moves.js';` и `import { createChat } from './game-chat.js';`.

2. **Зритель** (`state.you === 'spectator'`):
   - `boardApi.setOrientation(state.you === 'black' ? 'black' : 'white')`;
   - панели: внизу всегда цвет `bottom = state.you === 'black' ? 'black' : 'white'`, сверху — другой. Переписать `panelFor(color)`: `return color === bottom ? youPanel : oppPanel`;
   - `actionsCard`, `drawBanner`, `depPanel`, `depHint` скрыты (`hidden = true`) всегда; клики по доске ничего не делают;
   - над доской `div.spectator-badge` с текстом «Вы смотрите партию» (показывать только зрителю);
   - модалка итога для зрителя: заголовок «Партия завершена»; строка результата: `white` → «Победили белые», `black` → «Победили чёрные», `draw` → «Ничья», `aborted` → «Партия отменена»; плюс `END_REASON_RU`. Строки Elo и награды зрителю не показывать.

3. **Ходы:** вместо карточки «Лента партии» (`feedCard`) — `div.card` с заголовком «Ходы» и контейнером для `createMoveList(movesBox, { onSelect: viewEvent })`. Функции `pushFeed`/`renderFeed` и их вызовы удалить.
   - После первой загрузки состояния: `GET /games/<id>/events` → `moves.setEvents(res.events)`.
   - После каждого `applyState`, где версия выросла: `GET /games/<id>/events?after_seq=<moves.lastSeq()>` → `moves.appendEvents(res.events)`. Не через `enqueue`; ошибки игнорировать (`console.error`).

4. **Просмотр позиции:** переменная `viewing` (событие или `null`).
   - `viewEvent(ev)`: `viewing = ev`; `moves.select(ev.seq)`; показать `div.view-banner` над доской с текстом «Просмотр позиции · ход <номер>» (номер = `Math.floor((ev.ply - 1) / 2) + 1`) и кнопкой `btn btn-ghost btn-sm` «К текущей позиции» → `viewing = null; moves.select(null);` скрыть баннер, `boardRender()`.
   - В `boardRender()` в самом начале: если `viewing !== null` → `boardApi.render({ ...state, board: viewing.board, check_square: viewing.check_square, last_action: viewing.kind === 'move' ? { kind: 'move', ...viewing.payload } : (viewing.kind === 'dep' ? { kind: 'dep', ...viewing.payload } : null) }, {})` и `return`.
   - Пока `viewing !== null`, клики по доске игнорируются.
   - Если `applyState` получает состояние с новой версией и пользователь — игрок, чей сейчас ход, автоматически выйти из просмотра.

5. **Чат:** `div.card` с заголовком «Чат» под карточкой ходов; `const chat = createChat(chatBox, { gameId: id, canWrite: true }); chat.load();`. В `onMessage` WebSocket: `msg.type === 'chat'` → `chat.onWsChat(msg.data)` (не через `enqueue`).

6. **В конец `frontend/css/game.css` дописать дословно:**
```css
.spectator-badge { padding: 6px 10px; border-radius: 10px; background: rgba(139,92,246,.15); color: var(--text); font-size: 13px; text-align: center; margin-bottom: 8px; }
.view-banner { display: flex; gap: 8px; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: 10px; background: color-mix(in srgb, var(--gold) 15%, transparent); font-size: 13px; margin-bottom: 8px; }
.view-banner[hidden], .spectator-badge[hidden] { display: none; }
```

Всё остальное поведение `game.js` (очередь `enqueue`, правило версий, деп, часы, модалка итога для игроков) сохранить без изменений.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
