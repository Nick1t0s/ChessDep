# Цель
Секция «Кейсы» в карточке коллекции админки: список кейсов с дропами и шансами, создание, изменение, удаление, редактирование дропов и автовеса.

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
Создать: `frontend/js/admin/cases.js`. Только этот файл.

# Контракт
Классы из `frontend/css/admin.css` (создаётся параллельной задачей, НЕ менять и НЕ создавать его): `.admin-table` (таблица), `.admin-form` (вертикальная форма), `.admin-row` (горизонтальный ряд кнопок или полей), `.admin-section` (блок с отступом), `.admin-muted` (мелкий серый текст), `.status-draft`, `.status-released`, `.status-retired` (цвет статуса, ставить на `span` вместе с `pill`). Поля ввода в формах — `input`/`select`/`textarea` внутри `div.field` с `label`.

Экспорт (контракт, его вызывает `catalog.js` другого исполнителя):
```js
export function renderCasesSection(container, detail, reload)
// container: HTMLElement — пустой контейнер секции
// detail: { id, status: 'draft'|'released'|'retired', items: def[], cases: [{id, code, name, price, is_active, sort, drops: [{item_def_id, weight}]}] }
// reload: () => Promise<void> — перерисовать карточку коллекции после изменения
```

API:
- `POST /admin/collections/<detail.id>/cases` тело `{code, name, price, sort}`;
- `PATCH /admin/cases/<id>` тело — изменённые из `{name, price, is_active, sort}`;
- `DELETE /admin/cases/<id>`;
- `PUT /admin/cases/<id>/drops` тело `[{item_def_id, weight}]`;
- `POST /admin/cases/<id>/drops/auto` тело `{kind: null | 'piece_skin' | 'board_skin'}`.

Разметка внутри `container`: `h3` «Кейсы». Для каждого кейса `div.card`:
- `h4` (name), `p.admin-muted` («<code> · цена <fmtCrystals(price)> · <is_active ? 'активен' : 'выключен'> · порядок <sort>»);
- `table.admin-table` дропов с колонками Скин (`name` скина из `detail.items` по `item_def_id`), Вес, Шанс (`(weight / sum * 100).toFixed(2) + '%'`, где `sum` — сумма весов кейса). Нет дропов → `p.admin-muted` «Дропов нет»;
- `div.admin-row` кнопок:
  - «Изменить» (всегда): `openModal` с полями name, price (`number min=1`), sort (`number`), `is_active` (checkbox). Сохранить → `PATCH`;
  - только если `detail.status === 'draft'`:
    - «Автовеса» — `openModal` с `select` (Все → null, Фигуры → piece_skin, Доски → board_skin) → `POST drops/auto`;
    - «Дропы вручную» — `openModal` со списком всех `detail.items`: в каждой строке `span` с названием и `input type=number min=0 step=1`, значение = текущий вес или 0. Сохранить → `PUT drops` со всеми строками, где вес > 0;
    - «Удалить» (`btn-danger`) → `confirmModal` → `DELETE`.

После каждого успешного действия: `toast('Готово', 'success')` и `await reload()`.

Форма «Новый кейс» (`form.admin-form`, есть в любом статусе): code, name, price (`number min=1`, по умолчанию 100), sort (`number`, по умолчанию 0), кнопка «Создать» → `POST`, затем `reload()`. Не забыть `event.preventDefault()`.

Импорты — только из `../api.js`, `../dom.js`, `../toast.js`, `../modal.js`, `../format.js`. Ошибки — `toast(e.message, 'error')`.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
