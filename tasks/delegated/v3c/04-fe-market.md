# Цель
Маркет v3: лоты кейсов и фильтр вида.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 маркет, 6.3 `/market`), `frontend/js/market.js`, `frontend/js/market-item.js`.

# Область
`frontend/js/market.js`, `frontend/js/market-item.js`.

# Что сделать
- `market.js`: добавить фильтр вида `kindSel = mkSelect([['', 'Все'], ['piece', 'Фигуры'], ['board', 'Доски'], ['case', 'Кейсы']])` → параметр `kind` (рядом с остальными фильтрами, в ту же логику сброса страницы). Карточка лота: если `l.item.kind === 'case'` — `invItemCard(l.item, …)` (из `./items.js`; у `ListingItemOut` те же поля `kind/def/case/exterior`), ссылка на `/market-item.html?case=<l.item.case.id>`; иначе как сейчас, ссылка `?def=<id>` (сохранить существующий параметр, если он иначе называется — оставить как есть).
- `market-item.js`: если в query есть `case` — `GET /market/cases/{id}`, заголовок — `data.case.name`, превью `casePreview(data.case)`; иначе — как сейчас (`/market/defs/{id}`). Остальная логика (статистика, лоты, покупка) — общая, по полям `stats`, `listings`, `sales`.

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
