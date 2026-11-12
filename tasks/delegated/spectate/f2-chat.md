# Цель
Фронтенд-модуль чата партии `createChat`.

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
Создать: `frontend/js/game-chat.js`, `frontend/css/chat.css`. Больше ничего.

# Контракт и что сделать
Сигнатура — дословно контракт п. 8 (`createChat(container, { gameId, canWrite })` → `{ load, onWsChat }`). Сообщение — `ChatMessageOut` из контракта п. 6.

- Модуль делает `clear(container)` и строит: `div.chat-list` (прокручиваемый) и, если `canWrite`, `form.chat-form` из `input` (`type=text`, `maxlength=300`, `placeholder: 'Сообщение…'`, `autocomplete: 'off'`) и кнопки `btn btn-gold btn-sm` «Отправить».
- Строка сообщения `div.chat-msg.role-<role>`: `span.chat-time` (`HH:MM` из `created_at` через `toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })`), `b.chat-login` (login), `span.chat-role` («белые» / «чёрные» / «зритель»), `span.chat-body` (body). Всё — только текстом.
- Хранить `Set` id показанных сообщений; повтор по id игнорировать.
- `load()`: `GET /games/<gameId>/chat?limit=50` → показать `items` (они уже по возрастанию id), прокрутить вниз. Ошибка → `toast`.
- Отправка (`submit`, `event.preventDefault()`): текст `trim()`; пусто → ничего; `POST /games/<gameId>/chat` `{ body }` → показать ответ как сообщение (через тот же путь с проверкой дубля), очистить поле. Ошибка (в т. ч. 429) → `toast(e.message, 'error')`, текст не стирать. Пока запрос идёт — кнопка `disabled`.
- `onWsChat(message)` — показать (с проверкой дубля), прокрутить вниз, только если пользователь был внизу списка (`list.scrollHeight - list.scrollTop - list.clientHeight < 40`).
- Импорты — только из `./api.js`, `./dom.js`, `./toast.js`.

`frontend/css/chat.css`, дословно:
```css
.chat-list { height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; font-size: 13px; padding-right: 4px; }
.chat-msg { line-height: 1.35; word-break: break-word; }
.chat-time { color: var(--muted); font-family: var(--mono); font-size: 11px; margin-right: 6px; }
.chat-login { margin-right: 4px; }
.chat-role { color: var(--muted); font-size: 11px; margin-right: 6px; }
.chat-msg.role-white .chat-login { color: #f4f6ff; }
.chat-msg.role-black .chat-login { color: #ff5470; }
.chat-msg.role-spectator .chat-login { color: var(--muted); }
.chat-form { display: flex; gap: 6px; margin-top: 8px; }
.chat-form input { flex: 1; min-width: 0; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line); background: rgba(255,255,255,.03); color: var(--text); }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
