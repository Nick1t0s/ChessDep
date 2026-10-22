# task-006a — Фронтенд: каркас, вход, лобби, игровой экран

Прочитай перед работой: `docs/TZ.md` версии 1.1 — разделы 3 (правила депа — чтобы понимать UI), 4.4 (как рисовать скины), 7 (безопасность фронта), 9.2–9.6 (API партий), 10 (фронтенд целиком).

Бэкенд готов и проверен: **вся** логика (легальные ходы, шансы, допустимость депа, часы, результат) приходит с сервера. Фронт только рисует и отправляет действия.

## Правила для исполнителя (жёстко)
1. Чистые HTML + CSS + ES-модули (`<script type="module">`). Без сборки, фреймворков, npm, CDN, внешних шрифтов.
2. **DOM только через хелпер `h()`** (п. 2.1) и `textContent`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, `setAttribute("style", …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>`/`<style>`.
3. Динамические цвета (скины) — только через `el.style.setProperty("--var", value)`. CSP это разрешает, а атрибут `style` — нет.
4. В браузере ничего не хранится: никаких `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`. Состояние живёт в памяти страницы, а при перезагрузке всё запрашивается заново.
5. `Math.random` запрещён полностью (тест это проверяет). Анимации детерминированы.
6. Фронт **ничего не вычисляет** из игровой логики: не парсит FEN, не считает шансы, не решает, легален ли ход. Всё есть в ответах сервера.
7. Тексты интерфейса — на русском. Сообщения ошибок берутся из `error.message` ответа сервера.
8. Вёрстка должна работать от 360 px ширины, тапы ≥ 44 px.
9. Если что-то неясно — остановись и спроси.

---

## 0. Маленькая добавка в бэкенд

`GET /api/v1/config` (без авторизации, файл `app/api/config.py`) → `{"time_controls": [...из настройки...], "dep_limit": 10}`.

Тест `test_config_public` (в `tests/test_security.py`): без cookie 200, `time_controls == DEFAULTS["time_controls"]`, `dep_limit == 10`.

Расширить `tests/test_frontend_static.py`:
- добавить запреты `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function`, а также `setAttribute("style"` и `setAttribute('style'`;
- проверять **все** `*.js` и `*.html` во `frontend/` рекурсивно (уже так).

## 1. Файлы

```
frontend/
  index.html  login.html  register.html  game.html  invite.html  admin.html (заглушка остаётся)
  css/base.css         # токены, сброс, типографика, кнопки, поля (расширить существующий)
  css/layout.css       # шапка, мобильный таб-бар, контейнер
  css/components.css   # модалки, тосты, карточки, бейджи, спиннер
  css/board.css        # доска, клетки, фигуры, подсветки, анимации депа
  css/game.css         # раскладка игрового экрана, панели игроков, часы
  css/lobby.css
  js/api.js            # есть; не менять поведение, можно добавить экспорт
  js/dom.js  js/layout.js  js/toast.js  js/modal.js  js/format.js  js/pieces.js
  js/board.js  js/ws.js  js/dep-fx.js
  js/index.js  js/login.js  js/register.js  js/game.js  js/invite.js
```
Каждая страница подключает нужные CSS через `<link>` и ровно один модуль `js/<page>.js`.

## 2. Общие модули

### 2.1 `js/dom.js`
```js
export function h(tag, attrs = {}, ...children)
```
- `attrs.class` (строка или массив, ложные значения пропускаются), `id`, `type`, `disabled`, `title`, `href`, `value`, `name`, `role`, `tabindex`, `aria-*` и `data-*` → атрибуты;
- ключи `onClick`, `onInput`, `onSubmit`, `onKeydown` → `addEventListener` с событием в нижнем регистре;
- `href`: разрешены только строки, начинающиеся с `/` (но не `//`) или `#`, иначе `throw Error`;
- children: строки и числа → `document.createTextNode`, `Node` → как есть, `null`/`false` пропускаются, массивы разворачиваются.

```js
export function clear(el)          // while (el.firstChild) el.firstChild.remove()
export function $(selector, root = document)
```

### 2.2 `js/format.js`
- `fmtCrystals(n)` → `"1 250 ◈"` (`toLocaleString("ru-RU")`);
- `fmtClock(ms)`: `ms ≥ 10000` → `m:ss`; `ms < 10000` → `s.t` с десятыми (`"9.4"`); ниже нуля показывать `0.0`;
- `END_REASON_RU`:
  - `checkmate` «Мат»;
  - `stalemate` «Пат»;
  - `insufficient_material` «Недостаточно материала»;
  - `fifty_move` «Правило 50 ходов»;
  - `threefold` «Троекратное повторение»;
  - `resign` «Сдача»;
  - `timeout` «Время вышло»;
  - `timeout_vs_insufficient` «Время вышло, но у соперника недостаточно материала»;
  - `agreement` «Ничья по соглашению»;
  - `abort` «Партия отменена»;
  - `abort_no_first_move` «Партия отменена: не сделан первый ход»;
- `PIECE_NAME_RU`: `{P: "Пешка", N: "Конь", B: "Слон", R: "Ладья", Q: "Ферзь", K: "Король"}`;
- `DEP_REASON_RU`:
  - `WOULD_CHECK_OPPONENT` «Даст шах сопернику»;
  - `NOT_YOUR_TURN` «Сейчас не ваш ход»;
  - `DEP_ALREADY_USED_THIS_TURN` «Деп в этом ходу уже сделан»;
  - `DEP_LIMIT_REACHED` «Лимит депов исчерпан»;
  - `GAME_NOT_ACTIVE` «Партия завершена».

### 2.3 `js/pieces.js`
```js
const WHITE = {K:"♔", Q:"♕", R:"♖", B:"♗", N:"♘", P:"♙"};  // контурные
const BLACK = {K:"♚", Q:"♛", R:"♜", B:"♝", N:"♞", P:"♟"};  // сплошные
export function glyph(piece, color)   // + "︎" (текстовый, не эмодзи)
export const DEFAULT_PIECE_COLOR = {white: "#f4f6ff", black: "#ff5470"};
export const DEFAULT_BOARD = {light: "#454f77", dark: "#262e4d"};
export function pieceColor(loadout, piece, color)
    // loadout[piece]?.asset?.type === "stub" ? asset.color : DEFAULT_PIECE_COLOR[color]
export function boardColors(loadout)
    // loadout.board?.asset?.type === "stub" ? {light, dark} : DEFAULT_BOARD
```
Сторона различается **формой** глифа (TZ 4.4), поэтому белые заглушки у обоих игроков остаются читаемыми. У всех глифов в CSS — тёмная обводка: `text-shadow: 0 0 2px #000, 0 0 1px #000`. Тогда белая фигура видна и на белой доске-заглушке.

### 2.4 `js/toast.js`, `js/modal.js`
- `toast(message, kind = "info")`, `kind ∈ info | success | error`; стек в правом верхнем углу (на мобилке — сверху на всю ширину); максимум 4; исчезает через 3.5 с. Анимации `tin`/`tout` взять из `legacy/templates/fx/toast-stack.html`.
- `openModal({title, body, actions, dismissible = true})` → функция `close()`. `body` — `Node`. `actions` — `[{label, kind: "gold" | "ghost" | "danger", onClick}]`; кнопка закрывает модалку, если `onClick` не вернул `false`. Закрытие по Esc и клику по фону, если `dismissible`. Фокус на первой кнопке. Вид и анимации — `legacy/templates/fx/modal-result.html` (`pop`, `shake`).
- `confirmModal(title, text, okLabel, kind = "gold") → Promise<boolean>`.

### 2.5 `js/layout.js`
```js
export async function initLayout({ auth = "required", active = "" }) -> me | null
export function setBalance(n)
```
- `auth: "required"` → `GET /me`, а на 401 `api.js` уже перенаправит на логин. `"optional"` → ошибка 401 даёт `null` без редиректа (для этого добавь в `api.js` параметр `{ redirectOn401: false }`, по умолчанию `true`). `"none"` — без запроса.
- Шапка `header.topbar`:
  - слева логотип «ChessDep» (ссылка на `/index.html`);
  - ссылки: «Играть» `/index.html`, «Кейсы» `/cases.html`, «Инвентарь» `/inventory.html`, «Апгрейд» `/upgrade.html`, «Маркет» `/market.html`, «Лидеры» `/leaderboard.html` (страницы, кроме первой, появятся в 006b — ссылки уже есть);
  - справа баланс, бейдж непросмотренных подарков (`GET /me/gifts/unseen-count`, если > 0, ссылка `/gifts.html`), логин (ссылка `/profile.html`), «Админка» (только при `role === "admin"`), кнопка «Выйти» (`POST /auth/logout` → `/login.html`).
- Ссылка раздела `active` подсвечена.
- До 640 px верхние ссылки скрываются, вместо них нижний таб-бар (`nav.tabbar`, `position: fixed`, учитывать `env(safe-area-inset-bottom)`) с 5 пунктами: Играть, Кейсы, Инвентарь, Маркет, Профиль.

## 3. Вход и регистрация
Существующие `login.html`/`register.html` перевести на `layout.js` (`auth: "none"`, без ссылок разделов) и общие стили. Логика та же. Если пользователь уже залогинен (`GET /me` с `redirectOn401: false` вернул пользователя) → сразу `safeNext()`.

## 4. Лобби `index.html` + `js/index.js` (`auth: "required"`, `active: "play"`)

Блоки сверху вниз:
1. **Активная партия:** `GET /me/active-game`; если есть — заметная карточка «У вас идёт партия» с кнопкой «Вернуться» → `/game.html?id=…`. Остальные кнопки игры при этом скрыты.
2. **Играть онлайн:** контроли времени из `GET /config`, по кнопке на каждый (например «3+2»), крупные.
   - По клику `POST /matchmaking/queue`, карточка переходит в режим поиска: «Ищем соперника · 3+2 · 0:07» (счётчик секунд — от момента клика, локально), кнопка «Отмена» (`DELETE /matchmaking/queue`).
   - Поллинг `GET /matchmaking/status` раз в 1 с: `matched` → `location.href = /game.html?id=…`; `idle` → выйти из режима поиска с тостом «Поиск отменён».
   - На `pagehide` во время поиска — `fetch("/api/v1/matchmaking/queue", {method: "DELETE", credentials: "same-origin", keepalive: true})`.
   - При открытии лобби, если статус уже `queued` (обновили страницу), сразу показать режим поиска.
3. **Сыграть с другом:** выбор контроля времени + «Создать приглашение» → `POST /invites`.
   - Показать ссылку `location.origin + "/invite.html?code=" + code` в поле только для чтения, кнопку «Копировать» (`navigator.clipboard.writeText`, тост «Скопировано»; если `navigator.clipboard` нет — а по http с другой машины его нет — выделить текст в поле и показать тост «Скопируйте ссылку вручную») и обратный отсчёт до `expires_at`, кнопку «Отменить» (`DELETE /invites/{code}`).
   - Поллинг `GET /me/active-game` раз в 2 с; появилась партия → переход в неё.
   - Истекло → карточка «Приглашение истекло».
4. **Ежедневный бонус:** кнопка активна, если `me.daily_bonus_available_at === null`; иначе текст «Следующий бонус через 5 ч 12 мин», пересчитываемый раз в минуту. По клику `POST /me/daily-bonus` → `setBalance`, тост.

Состояния карточек (обычное / поиск / приглашение) переключаются CSS-классами. Таймеры очищаются при смене состояния.

## 5. Приглашение `invite.html` + `js/invite.js` (`auth: "required"`)
- Код из `?code=`, проверка `^[a-z2-9]{10}$`; иначе — сообщение «Некорректная ссылка».
- Карточка «Вас пригласили сыграть» и кнопка «Принять» → `POST /invites/{code}/accept` → переход в партию.
- Ошибки (`INVITE_EXPIRED`, `INVITE_OWN`, `INVITE_NOT_FOUND`, `ALREADY_IN_GAME`) — текстом из `message` на карточке. При `ALREADY_IN_GAME` — ссылка «Вернуться в свою партию».

## 6. Игровой экран `game.html` + `js/game.js`

### 6.1 Раскладка
- Десктоп (≥ 900 px): слева доска (квадрат, `min(100vw - 32px, 100vh - 140px, 720px)`), справа колонка 320 px.
- Мобилка: столбец — панель соперника, доска на всю ширину, панель «вы», кнопки действий.
- Панель игрока: глиф короля его цвета, логин, Elo, «депов N/10», часы (крупный моно-шрифт). У ходящего часы подсвечены, при < 10 с — красные.
- Соперник всегда сверху, вы снизу.
- Колонка или блок действий:
  - кнопка **«Деп»**;
  - «Предложить ничью»;
  - «Сдаться»;
  - «Отменить партию» — только при `ply < 2`;
  - лента событий партии;
  - индикатор соединения («Соединение потеряно, переподключаемся…»).
- Визуальная основа: `legacy/templates/layout/board-skeleton.html` (классы клеток и подсветок), `legacy/templates/chess/match-hud.html` (раскладка), `legacy/templates/chess/board-upgrade-fx.html` (анимации), `legacy/templates/chess/upgrade-linear-race.html` (бар шанса).

### 6.2 `js/board.js` — рендер доски
```js
export function createBoard(container, { orientation, onSquareClick }) -> {
  render(state, { selected, hints, captures, depPickable }),
  squareEl(square),       // DOM-элемент клетки по имени "e4"
  setOrientation(color),
}
```
- 64 `button.sq` создаются **один раз**. `render` только меняет классы и содержимое глифа. Каждой клетке `data-square="e4"` и `aria-label="e4, белый конь"` (или `"e4, пусто"`).
- Ориентация: `white` — a1 внизу слева; `black` — h8 внизу слева (доска перевёрнута). Координаты (буквы и цифры) по краям следуют ориентации.
- Цвета доски: `boardColors(state.players[state.you].loadout)` → `board.style.setProperty("--light" / "--dark", …)`.
- Фигура: `span.glyph.side-white|side-black` с `glyph()`, цвет — `pieceColor(state.players[color].loadout, piece, color)` через `--piece-color`.
- Подсветки (классы из `board-skeleton.html`):
  - `.last` — клетки from/to, если `last_action.kind === "move"` (from/to взять из `last_action.uci`: первые 2 и следующие 2 символа — это разбор строки ответа сервера, а не шахматная логика);
  - `.last-dep` — клетка последнего депа;
  - `.check` — `check_square`;
  - `.sel` — выбранная;
  - `.hint` — цель хода на пустую клетку;
  - `.cap` — цель хода на занятую;
  - `.dep-pick` — фигуры, доступные для депа (пульсирующая рамка `aimpulse`).

### 6.3 Состояние и синхронизация (`js/game.js`)
- `id` из `?id=` (проверка uuid-регэкспом, иначе сообщение и ссылка в лобби).
- Загрузка: `GET /games/{id}` → `applyState(state)`. Потом открыть WebSocket.
- **Единое правило:** `applyState(s)` применяет состояние, только если `s.version > current.version` (или текущего ещё нет). Это защищает от перепутанного порядка HTTP-ответов и WS-сообщений.
- После каждого `applyState`: перерисовать доску, панели, кнопки, часы. Если в состоянии `status !== "active"` и модалка итога ещё не показана — показать её (п. 6.8).

### 6.4 `js/ws.js`
```js
export function connectGame(gameId, { onMessage, onStatus }) -> { close() }
```
- URL: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/games/${gameId}`.
- Каждые 25 с отправлять `{"type": "ping"}`.
- Сервер отклоняет чужого или незалогиненного ещё на handshake (HTTP 403). Браузер в этом случае видит обычный обрыв с кодом 1006, неотличимый от проблем сети. Поэтому на **любое** закрытие: сделать `GET /games/{id}` через `api()` с `redirectOn401: false`. Ответ 401, 403 или 404 → `onStatus("forbidden")`, без переподключения. Иначе → `onStatus("reconnecting")` и переподключение с задержками 1, 2, 5, 10, 10, … с (ошибка самого GET из-за сети — тоже переподключение). После успешного `open` → `onStatus("online")`. Сервер сам присылает актуальное `state` при подключении, поэтому после переподключения доп. запрос не нужен.
- Сообщения передаются в `onMessage` строго по порядку получения.

### 6.5 Очередь сообщений и анимации депа
Анимация депа длится ~2.6 с и должна показываться **обоим** игрокам. Состояние, пришедшее во время анимации, нельзя рисовать раньше её окончания: иначе фигура изменится до анимации.

Поэтому в `game.js` все входящие события проходят через **последовательную очередь** (`let chain = Promise.resolve(); function enqueue(fn) { chain = chain.then(fn).catch(console.error); }`):
- WS `state` → `enqueue(() => applyState(data))`;
- WS `dep`:
  - если `data.by !== state.you` → `enqueue(() => playDep(data))`;
  - если `data.by === state.you` → игнорировать (свою анимацию запускает HTTP-ответ, см. ниже);
- WS `game_over` → `enqueue(() => rememberGameOver(data))` (данные для модалки итога: Elo и награды);
- собственный деп: при нажатии «Депнуть» сразу `enqueue(async () => { const res = await api(POST /dep); await playDep(res); applyState(res.state); })`. Пока этот шаг выполняется, WS-сообщения встают в очередь **за ним** и применятся после анимации. Свою же `state` с той же версией правило из п. 6.3 отбросит.
- Ошибка запроса депа → тост с `message`, при `VERSION_CONFLICT` — перезапросить `GET /games/{id}`.

### 6.6 Ход
- Режим `idle`. Клик по своей фигуре в свой ход (партия активна, не идёт анимация) → `selected`. Подсветка `hints`/`captures` из `state.legal_moves`: ходы, начинающиеся с выбранной клетки; цель `.cap`, если на ней стоит фигура (по `state.board`).
- Клик по цели:
  - среди ходов на эту клетку есть варианты с 5-м символом (превращение) → модалка выбора из 4 фигур (глифы своего цвета: Ферзь, Ладья, Слон, Конь → суффикс `q r b n`);
  - иначе отправка `POST /move {uci, expected_version: state.version}` через ту же очередь (`enqueue`) → `applyState(response)`.
- Клик по другой своей фигуре → переключить выбор; по чему-то ещё → сброс в `idle`.
- Ошибка хода → тост; `VERSION_CONFLICT` или `TIME_EXPIRED` → перезапросить состояние.
- Пока запрос в полёте — доска не реагирует на клики (флаг `busy`).

### 6.7 Деп — интерфейс
1. Кнопка «Деп · осталось N» активна, если: партия активна, `turn === you`, `!deps.used_this_turn`, `used < deps.limit`, нет `busy`. Подсказка на неактивной кнопке — причина из `DEP_REASON_RU`.
2. Клик → `GET /games/{id}/dep-options`. `available === false` → тост с причиной. Иначе режим `dep_pick_piece`: фигуры из `pieces` подсвечены `.dep-pick`, над доской подсказка «Выберите фигуру для депа» и кнопка «Отмена». Клик вне подсвеченных фигур — отмена.
3. Клик по фигуре → панель целей (справа на десктопе, нижний лист на мобилке): строки «глиф цели · название · шанс `chance_text`». Недопустимые (`allowed=false`) неактивны, с подписью причины.
4. Выбор цели → блок подтверждения: «Конь → Ферзь · шанс 33.33% · при провале фигура сгорит» и кнопки «Депнуть» / «Назад».
5. «Депнуть» → п. 6.5.

`js/dep-fx.js`:
```js
export async function playDep(boardApi, event, { mine })
// event: {square, from, to, success, chance, roll_value, by}  (DepResultOut и WS dep совместимы по этим полям)
```
1. Над доской оверлей-бар (основа `upgrade-linear-race.html`): полоса 0–100 %, золотая win-зона слева шириной `chance * 100 %`, подпись «Конь → Ферзь · 33.33 %» и «Соперник депает…», если `!mine`.
2. Курсор едет слева направо 1.8 с с `cubic-bezier(.15,.85,.25,1)` и останавливается на `roll_value * 100 %` (CSS-переход `left`, конец перехода — `transitionend`, с запасным `setTimeout` на 2 с).
3. Затем 0.8 с на клетке `square`:
   - успех — `newpop` + `ringburst`, глиф меняется на целевую фигуру;
   - провал — `crack` и затухание глифа.
4. Оверлей убирается, промис резолвится. Новую позицию рисует последующий `applyState`.

### 6.8 Часы
- При каждом `applyState` запомнить `clocks` и `receivedAt = performance.now()`.
- Тик `requestAnimationFrame` (или `setInterval` 100 мс): у ходящего (`clocks.running`) показывать `ms - (performance.now() - receivedAt)`, у второго — значение как есть.
- `running === null` → оба статично.
- Ноль на клиенте — только отображение. Флаг ставит сервер, и итог придёт новым состоянием.

### 6.9 Прочие действия
- «Сдаться» → `confirmModal("Сдаться?", "Партия будет засчитана как поражение.", "Сдаться", "danger")` → `POST /resign`.
- «Предложить ничью» → `POST /draw/offer`, кнопка становится «Ничья предложена» (неактивна), пока `draw_offer_by === you`.
- `draw_offer_by === соперник` → баннер «Соперник предлагает ничью» с кнопками «Принять» / «Отклонить».
- «Отменить партию» (при `ply < 2`) → `POST /abort`.
- Все действия — через `enqueue`, с `expected_version`.

### 6.10 Итог партии
Модалка (`dismissible: false`):
- заголовок «Победа» (анимация `pop`), «Поражение» (`shake`) или «Ничья»; для `aborted` — «Партия отменена»;
- строка `END_REASON_RU[end_reason]`;
- Elo `1216 (+16)` и награда `+100 ◈` — из `game_over`, если WS-сообщение пришло; иначе только результат;
- кнопки «В лобби» и «Новая партия» (→ `/index.html`).

После итога `setBalance` по свежему `GET /me`.

### 6.11 Лента событий
Список последних 30 событий **за время сессии на странице**: при каждом новом состоянии, если `last_action` изменился, добавить строку: ход — `san` (например «♘ Nf3» — глиф фигуры ходившей стороны из `state.board` по клетке назначения); деп — «Деп: Конь → Ферзь — успех/провал»; плюс системные строки (предложение ничьей, итог). Полная история ходов с сервера — вне этой задачи.

## 7. Проверка
1. `make test` — все зелёные (151 старый + новый `test_config_public`; статический тест с расширенным списком запретов).
2. `make up`, затем вручную в двух браузерах (обычный + приватное окно) на `http://localhost:8080`:
   - регистрация двух игроков, оба нажимают «3+2» → оба попадают в одну партию;
   - ходы видны у соперника без перезагрузки; у чёрных доска перевёрнута;
   - деп у одного → анимация бара и результата видна **у обоих**, позиция меняется только после анимации;
   - превращение пешки (можно довести партию или проверить модалку на любой позиции перед превращением);
   - предложение ничьей → баннер у соперника → принятие → модалка итога у обоих;
   - сдача, отмена партии до первых ходов;
   - отключить сеть у одного (devtools → Offline) на 5 с → индикатор «Соединение потеряно», затем восстановление и актуальная позиция;
   - приглашение по ссылке в приватном окне;
   - мобильный вид 375 px (devtools): таб-бар снизу, доска на всю ширину, кнопки нажимаются.
3. В devtools → Application: Storage пуст, единственная cookie — `sid` (HttpOnly). В Console нет ошибок CSP.

В отчёте: что из п. 7.2 реально проверено вручную, а что нет (честно). Плюс список файлов, отступления и вопросы.
