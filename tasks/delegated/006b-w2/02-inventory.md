# Цель
Страница инвентаря: экипировка по слотам, список предметов с фильтрами и действия «Надеть», «Снять», «Продать», «Подарить», «Снять с продажи».

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
Создать: `frontend/inventory.html`, `frontend/js/inventory.js`, `frontend/css/inventory.css`.

# Контракт
`initLayout({ auth: 'required', active: 'inventory' })`, класс main: `wrap-wide inventory`, `<title>Инвентарь — ChessDep</title>`.

API:
- `GET /loadout` → `{P: Item|null, N, B, R, Q, K, board}`. `Item` = `{id, def, wear, exterior, status: 'owned'|'listed', equipped_slot: 'P'|'N'|'B'|'R'|'Q'|'K'|'board'|null, source, acquired_at}`, где `def` — объект скина (см. `frontend/js/items.js`).
- `PUT /loadout/<slot>` тело `{inventory_item_id: number|null}` → новый лоадаут.
- `GET /inventory?sort=<rarity|value|new>` и при выбранном фильтре `&kind=<piece_skin|board_skin>` → `Item[]`.
- `GET /me/listings?status=active` → `[{id, price, item: {id, ...}, ...}]` — нужен, чтобы найти id лота по id предмета.
- `POST /market/listings` тело `{item_id, price}`; `DELETE /market/listings/<listingId>`.
- `POST /gifts` тело `{item_id, to_login, note}` (`note` — строка или `null`).

Разметка сверху вниз:
1. `h('h1', { class: 'page-title' }, 'Инвентарь')`.
2. Карточка `.card` с заголовком «Экипировка»: сетка `div.inv-slots`, 7 ячеек в порядке P, N, B, R, Q, K, board. Ячейка `div.inv-slot`: подпись `h('div', { class: 'inv-slot-label' }, SLOT_RU[slot])`; если предмет есть — `itemCard(item.def, { exterior: item.exterior, extra: кнопка 'Снять' })` (кнопка `btn btn-ghost btn-sm`, по клику `PUT /loadout/<slot>` с `null`); иначе `div.slot-empty` с текстом «Пусто».
3. Карточка «Предметы»: строка фильтров `div.inv-filters`: `select` вида (Все → '', Фигуры → piece_skin, Доски → board_skin) и `select` сортировки (По редкости → rarity, По ценности → value, Новые → new). Ниже `div.item-grid`.
   Для каждого предмета `itemCard(item.def, { exterior: item.exterior, badge, extra })`:
   - `badge`: `'На маркете'`, если `status === 'listed'`; иначе `'Надето'`, если `equipped_slot`; иначе не передавать.
   - `extra` = `div.item-actions` с кнопками `btn btn-ghost btn-sm`:
     - статус `owned` и не надет → «Надеть»: слот = `def.kind === 'board_skin' ? 'board' : def.piece_type`, `PUT /loadout/<slot>` с `{inventory_item_id: item.id}`;
     - статус `owned` → «Продать»: `openModal` с полем цены (`input type=number min=1 max=10000000 step=1`), действие «Выставить» (`gold`): если цена не целое 1..10000000 → `toast('Цена от 1 до 10 000 000', 'error')` и вернуть `false`; иначе `POST /market/listings`;
     - статус `owned` → «Подарить»: `openModal` с полем логина (`input type=text maxlength=64`) и запиской (`textarea rows=3 maxlength=140`), действие «Подарить» (`gold`): пустой логин → тост ошибки и `false`; иначе `POST /gifts` с `note: текст || null`;
     - статус `listed` → «Снять с продажи»: найти лот в `GET /me/listings?status=active` по `listing.item.id === item.id`, `DELETE /market/listings/<id>`.
   Пустой список → `p.inv-empty` «Инвентарь пуст.» и ссылка `h('a', { href: '/cases.html', class: 'btn btn-gold btn-sm' }, 'Открыть кейс')`.
4. После любого успешного действия: `toast('Готово', 'success')` и перезагрузить и лоадаут, и список. Смена фильтра или сортировки перезагружает только список.
5. Модалка вставляется в `body`, а не в `main`, поэтому `body` модалки = `h('div', { class: 'inventory' }, ...)` — чтобы на поля действовали стили ниже.

`frontend/css/inventory.css`, дословно:
```css
.inventory .card { margin-bottom: 16px; }
.inv-slots { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.inv-slot { display: flex; flex-direction: column; gap: 6px; }
.inv-slot-label { font-size: 12px; color: var(--muted); font-weight: 600; }
.slot-empty { display: grid; place-items: center; height: 150px; border: 1px dashed var(--line); border-radius: 14px; color: var(--muted); font-size: 13px; }
.inv-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.inv-filters select { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel); color: var(--text); }
.item-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.inv-empty { color: var(--muted); margin-bottom: 8px; }
.inventory input, .inventory textarea { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); background: rgba(255,255,255,.03); color: var(--text); margin-top: 6px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
