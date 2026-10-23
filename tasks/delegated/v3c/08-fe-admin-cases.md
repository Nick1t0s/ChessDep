# Цель
Вкладка админки «Кейсы» v3: виды кейсов, лимиты, публикация, пул ежедневной награды.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Кейс», 5 «Кейс», «Ежедневная награда», 6.1 `AdminCaseOut`, 6.2 `CaseCreateIn`/`CasePatchIn`/`AutoDropsIn`/`DailyPoolIn`, 6.3 админ), `frontend/js/admin/cases.js` (текущий — переработать).

# Область
Только `frontend/js/admin/cases.js`.

# Что сделать
- `render(root)`: параллельно `GET /admin/cases`, `GET /admin/item-defs`, `GET /admin/sets`, `GET /admin/daily-reward-pool`.
- Форма «Новый кейс»: код, название, цена (100), порядок (0), «Вид» (select `set` «По набору» / `collection` «По коллекции» / `custom` «Особый»); при `set` — select набора (небазовые наборы из `/admin/sets`, статус не `retired`), при `collection` — select коллекции: id коллекций есть только в детали набора, поэтому при `render` загрузи `GET /admin/sets/{id}` для каждого небазового не `retired` набора и собери `collections[]` (`id`, `name`, имя набора); эти же данные используй в «Автовеса» для `custom`; «Тираж» (пусто = без лимита), «Начало продаж», «Конец продаж» (`input type="datetime-local"`, пусто = null; в API — `new Date(value).toISOString()`). → `POST /admin/cases` с `{code, name, price, sort, kind, set_id, collection_id, stock_limit, sale_starts_at, sale_ends_at}` (лишние ссылки — `null`).
- Карточка кейса: название, статус (`draft` Черновик / `on_sale` В продаже / `off_sale` Снят с продажи) и пометка «Продаётся сейчас» при `on_sale_now`; строка: вид (`CASE_KIND_RU` из `../items.js`) и источник (`set.name` / `collection.name`), цена, порядок; лимиты: `'Продано ' + sold_count + (stock_limit ? ' из ' + stock_limit : '')`, окно продаж датами `toLocaleString('ru-RU')`; таблица дропов как сейчас.
- Кнопки: всегда «Изменить» (модалка: название, цена, порядок, тираж, начало, конец → `PATCH`, пустые поля лимитов — `null`); `draft`: «Автовеса», «Дропы вручную», «Опубликовать», «Удалить»; `on_sale`: «Снять с продажи» (`POST …/unpublish`); `off_sale`: «Опубликовать» (`POST …/publish`).
- «Автовеса»: для `set`/`collection` — сразу `POST …/drops/auto` с `{}` (подтверждение `confirmModal`); для `custom` — модалка с чекбоксами наборов и коллекций (по данным выше) → `{ set_ids, collection_ids }`, ничего не выбрано — `toast('Выберите хотя бы один набор или коллекцию', 'error')`.
- «Дропы вручную»: как сейчас, список скинов из `/admin/item-defs`, сгруппированный по `def.set.name` (и внутри по `def.collection?.name ?? 'Доски'`); для `set`/`collection` показывать только скины своего источника (`def.set.code === case.set.code` / `def.collection?.code === case.collection.code`).
- Секция «Ежедневная награда» внизу: текст «Игрок получает один кейс по весам после N побед за день» (N не показывать — просто текст без числа); таблица пула (кейс, вес, шанс = вес / сумма в % с 2 знаками); кнопка «Изменить пул» → модалка: для каждого не `draft` кейса поле веса (0 = не в пуле) → `PUT /admin/daily-reward-pool` массивом `{case_id, weight}` с весом > 0.

# Готово, когда
`bash scripts/check_frontend.sh` → `frontend check: OK`.

# Общие правила фронта
- Контракт API: `docs/contracts-collections.md` (п. 6 — формы ответов, п. 7 — что показывать). Поля и пути — дословно оттуда.
- DOM только через `h()` / `clear()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты в HTML. Цвета — только `el.style.setProperty(...)`.
- Фронт ничего не вычисляет из игровой логики (шансы, доступность — только из ответов API).
- Ошибки API — `toast(e.message, 'error')`. Тексты — по-русски, дословно как в задаче.
- Общий модуль `frontend/js/items.js` (правится параллельно задачей 01) будет экспортировать: `RARITIES`, `RARITY_RU`, `EXTERIOR_RU`, `SLOT_RU` (ключи `wP`…`bK` и `board: 'Доска'`), `WHITE_SLOTS`, `BLACK_SLOTS`, `LOADOUT_SLOTS` (13), `SIDE_RU`, `KIND_RU = { piece: 'Фигура', board: 'Доска', case: 'Кейс' }`, `CASE_KIND_RU = { set: 'Набор', collection: 'Коллекция', custom: 'Особый' }`, `skinPreview(def)` (фигура или доска), `casePreview(caseRef)`, `itemCard(def, opts)` (как сейчас), `invItemCard(item, opts)` — карточка предмета инвентаря `ItemOut` (скин или кейс; opts как у `itemCard`).
- Менять только файлы из «Область». Проверка: `bash scripts/check_frontend.sh` → `frontend check: OK`.
- Если что-то не сходится — остановиться и описать в SUMMARY, не придумывать.
