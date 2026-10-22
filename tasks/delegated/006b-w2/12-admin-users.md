# Цель
Вкладка админки «Пользователи»: поиск, карточка пользователя, бан/разбан, изменение баланса, выдача скина.

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
Создать: `frontend/js/admin/users.js`. Только этот файл.

# Контракт
Классы из `frontend/css/admin.css` (создаётся параллельной задачей, НЕ менять и НЕ создавать его): `.admin-table` (таблица), `.admin-form` (вертикальная форма), `.admin-row` (горизонтальный ряд кнопок или полей), `.admin-section` (блок с отступом), `.admin-muted` (мелкий серый текст), `.status-draft`, `.status-released`, `.status-retired` (цвет статуса, ставить на `span` вместе с `pill`). Поля ввода в формах — `input`/`select`/`textarea` внутри `div.field` с `label`.

Экспорт: `export async function mount(root)`.

API:
- `GET /admin/users?q=<строка>&page=1&limit=50` → `{items: [{id, login, email, role, is_banned, balance, elo, created_at, active_game_id}], total}`. Параметр `q` не передавать, если пусто; иначе через `encodeURIComponent`.
- `GET /admin/users/<id>` → те же поля + `items_owned`, `active_listings`, `ledger: [{id, delta, balance_after, reason, ref, actor_id, created_at}]`.
- `POST /admin/users/<id>/ban` тело `{reason}` (1–200 символов); `POST /admin/users/<id>/unban`.
- `POST /admin/users/<id>/balance` тело `{delta, comment}` (`delta` — целое ≠ 0; comment 1–200).
- `GET /item-defs` → `def[]` (все выпущенные скины). `POST /admin/users/<id>/grant-item` тело `{item_def_id}`.

Список (`renderList`):
- `div.admin-row`: `input type=text` (placeholder «логин или email») и кнопка «Найти»; Enter в поле тоже ищет.
- `p.admin-muted` «Найдено: total».
- `table.admin-table` с колонками ID, Логин, Email, Роль, Бан («Да» / «»), Баланс (`fmtCrystals`), Elo, Создан, и кнопка «Открыть».
- При открытии вкладки сразу выполнить поиск с пустым `q`.

Карточка (`renderDetail(id)`):
- «← К списку».
- `h2` (login), строки `p`: Email, Роль, Бан, Баланс, Elo, Скинов (`items_owned`), Активных лотов, Активная партия (id или «—»).
- `div.admin-row` действий:
  - «Забанить» (если не забанен, `btn-danger`): `openModal` с `textarea` причины, действие «Забанить»; пустая причина → тост и `false`;
  - «Разбанить» (если забанен);
  - «Изменить баланс»: `openModal` с `input type=number step=1` (delta) и `input type=text` (comment). Проверка: целое, не 0, comment не пуст;
  - «Выдать скин»: `openModal` с `select` из `GET /item-defs` (текст опции `name + ' · ' + RARITY_RU[rarity]`, значение id).

  После успеха: тост и `renderDetail(id)` заново.
- Секция «Операции»: `table.admin-table` по `ledger` с колонками Дата, Причина (`reason` как есть), Сумма (со знаком), Баланс после, Ref.

Импорты — только из `../api.js`, `../dom.js`, `../toast.js`, `../modal.js`, `../format.js`, `../items.js`. Ошибки — `toast(e.message, 'error')`.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
