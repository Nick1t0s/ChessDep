# Цель
Две вкладки админки: «Маркет» (просмотр лотов и снятие) и «Журнал» (действия администраторов).

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
Создать: `frontend/js/admin/misc.js`. Только этот файл.

# Контракт
Классы из `frontend/css/admin.css` (создаётся параллельной задачей, НЕ менять и НЕ создавать его): `.admin-table` (таблица), `.admin-form` (вертикальная форма), `.admin-row` (горизонтальный ряд кнопок или полей), `.admin-section` (блок с отступом), `.admin-muted` (мелкий серый текст), `.status-draft`, `.status-released`, `.status-retired` (цвет статуса, ставить на `span` вместе с `pill`). Поля ввода в формах — `input`/`select`/`textarea` внутри `div.field` с `label`.

Экспорт: `export async function mountMarket(root)` и `export async function mountAudit(root)`.

### mountMarket
- `GET /admin/market?limit=50` плюс `&status=<s>`, если выбран, и `&before_id=<next_cursor>` для «Ещё» → `{items: [{id, item_id, item_def_id, seller_id, price, status, buyer_id, fee, created_at, closed_at}], next_cursor: number|null}`.
- `select` статуса: Все → '', Активные → active, Проданные → sold, Снятые → cancelled. Смена перезагружает с начала.
- `table.admin-table` с колонками ID, Предмет (`item_id`), Скин (`item_def_id`), Продавец (`seller_id`), Цена (`fmtCrystals`), Статус, Покупатель (`buyer_id` или «—»), Комиссия (`fee` или «—»), Создан, и для `active` кнопка `btn btn-danger btn-sm` «Снять».
- Снять: `openModal` с `textarea` причины (обязательна) → `POST /admin/market/listings/<id>/cancel` тело `{reason}` → тост и перезагрузка.
- Кнопка «Ещё», пока `next_cursor !== null`, дописывает строки.

### mountAudit
- `GET /admin/audit?limit=50` и `&before_id=<next_cursor>` → `{items: [{id, admin_id, admin_login, action, target, payload, created_at}], next_cursor}`.
- `table.admin-table` с колонками Дата, Админ (`admin_login ?? 'CLI'`), Действие (`span.mono`), Объект, Данные: `h('code', { class: 'admin-muted' }, s)`, где `s = JSON.stringify(payload)`, обрезанная до 200 символов с `…` на конце, если длиннее.
- Кнопка «Ещё».

Импорты — только из `../api.js`, `../dom.js`, `../toast.js`, `../modal.js`, `../format.js`. Ошибки — `toast(e.message, 'error')`.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
