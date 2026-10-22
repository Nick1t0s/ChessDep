# Цель
Вкладка админки «Коллекции»: список коллекций, создание, карточка коллекции с выпуском/снятием/удалением и полным управлением скинами.

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
Создать: `frontend/js/admin/catalog.js`. Только этот файл. Секцию кейсов делает другой исполнитель в `frontend/js/admin/cases.js` — его НЕ создавать, только импортировать.

# Контракт
Классы из `frontend/css/admin.css` (создаётся параллельной задачей, НЕ менять и НЕ создавать его): `.admin-table` (таблица), `.admin-form` (вертикальная форма), `.admin-row` (горизонтальный ряд кнопок или полей), `.admin-section` (блок с отступом), `.admin-muted` (мелкий серый текст), `.status-draft`, `.status-released`, `.status-retired` (цвет статуса, ставить на `span` вместе с `pill`). Поля ввода в формах — `input`/`select`/`textarea` внутри `div.field` с `label`.

Импорт секции кейсов (контракт другого модуля, считать существующим):
```js
import { renderCasesSection } from './cases.js';
// renderCasesSection(container: HTMLElement, detail: AdminCollectionDetail, reload: () => Promise<void>): void
```

Экспорт: `export async function mount(root)` — показывает список коллекций.

API:
- `GET /admin/collections` → `[{id, code, name, description, status: 'draft'|'released'|'retired', created_at, released_at, retired_at, items_count, cases_count}]`.
- `POST /admin/collections` тело `{code, name, description}` → коллекция.
- `GET /admin/collections/<id>` → `AdminCollectionDetail` = поля коллекции + `items: def[]` + `cases: [{id, code, name, price, collection, is_active, sort, drops: [{item_def_id, weight}]}]`.
- `POST /admin/collections/<id>/release`, `POST /admin/collections/<id>/retire`, `DELETE /admin/collections/<id>`.
- `POST /admin/collections/<id>/items` тело `{code, name, kind, piece_type, rarity, value, asset, is_upgrade_target}`.
- `PATCH /admin/item-defs/<id>` тело — только изменённые поля из `{name, value, asset, is_upgrade_target, rarity}`; `DELETE /admin/item-defs/<id>`.

Список (`renderList(root)`):
- `table.admin-table` с колонками Код, Название, Статус (`span.pill.status-<status>` с текстом `STATUS_RU[status]`), Скинов, Кейсов и кнопка «Открыть» → `renderDetail(root, id)`. `STATUS_RU = { draft: 'Черновик', released: 'Выпущена', retired: 'Снята' }`.
- Под ней `div.card` «Новая коллекция»: `form.admin-form` с полями code (`input`, placeholder `winter-2026`), name, description (`textarea rows=3`) и кнопкой «Создать». Успех → `renderDetail(root, created.id)`. Не забыть `event.preventDefault()`.

Карточка (`renderDetail(root, id)`; `clear(root)`, затем `GET`):
- Шапка: кнопка «← К списку» (`btn btn-ghost btn-sm`), `h2` (name), `span.pill.status-<status>`, `p.admin-muted` (code и description).
- `div.admin-row` с действиями (каждое через `confirmModal`, затем запрос, тост и `renderDetail` заново):
  - «Выпустить» (только `draft`, кнопка `btn-gold`);
  - «Снять с выпуска» (только `released`);
  - «Удалить коллекцию» (только `draft`, `btn-danger`; после удаления → `renderList(root)`).
- Секция «Скины» (`div.admin-section`, `h3`): `table.admin-table` с колонками Превью (`skinPreview(def)`), Код, Название, Вид («Фигура <PIECE_NAME_RU[piece_type]>» или «Доска»), Редкость (`RARITY_RU`), Ценность, Цель апгрейда («Да» / «Нет»), и кнопки:
  - «Изменить»: `openModal` с формой name, value (`number min=1`), цвета (piece: одно поле `color`; board: поля `light` и `dark`; все `input type=text` со значением из `asset`), `is_upgrade_target` (`input type=checkbox`), и `select` rarity — только если коллекция `draft`. Сохранить → `PATCH` с изменёнными полями; `asset` всегда собирается целиком: `{type: 'stub', color}` или `{type: 'stub', light, dark}`;
  - «Удалить» (только `draft`) → `confirmModal` → `DELETE`.
- Форма «Новый скин» (`form.admin-form`):
  - code; name;
  - kind (`select`: piece_skin «Фигура», board_skin «Доска»);
  - piece_type (`select` P..K с `PIECE_NAME_RU`; скрыт через свойство `hidden`, когда выбран board_skin);
  - rarity (`select` по `RARITIES`/`RARITY_RU`);
  - value (`number min=1`, по умолчанию 20);
  - для piece_skin поле color (по умолчанию `#ffffff`), для board_skin поля light (`#ffffff`) и dark (`#e5e5e5`); ненужные скрывать свойством `hidden`;
  - `is_upgrade_target` (checkbox, отмечен).

  Отправка → `POST .../items` с `piece_type: null` для доски и `asset` по виду.
- Секция кейсов: `const casesBox = h('div', { class: 'admin-section' }); root.appendChild(casesBox); renderCasesSection(casesBox, detail, () => renderDetail(root, id));`.

Импорты — только из `../api.js`, `../dom.js`, `../toast.js`, `../modal.js`, `../format.js`, `../items.js`, `./cases.js`. Все ошибки API — `toast(e.message, 'error')`.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
