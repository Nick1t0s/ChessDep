# Цель
Апгрейд, подарки и выдача предмета админом под v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Апгрейд», 6.1 `ItemOut`, 6.2 `GrantItemIn`), `frontend/js/upgrade.js`, `frontend/js/gifts.js`, `frontend/js/admin/users.js` (функция выдачи предмета, `GET /item-defs`).

# Область
`frontend/js/upgrade.js`, `frontend/js/gifts.js`, `frontend/js/admin/users.js`.

# Что сделать
- `upgrade.js`: из инвентаря для выбора входов показывать только `item.kind === 'skin' && !item.bound && item.status === 'owned'` (остальное как сейчас). Цели — как сейчас (`/item-defs?upgrade_target=true`).
- `gifts.js`: карточку подаренного предмета рисовать `invItemCard(g.item, …)` из `./items.js` (поле `g.item` — `ListingItemOut` с `kind/def/case/exterior`), вместо прямого `itemCard(g.item.def, …)`.
- `admin/users.js`, модалка выдачи: селект «Что выдать»: `skin` «Скин» / `case` «Кейс». Для скина — как сейчас список из `GET /item-defs` → тело `{ item_def_id }`; для кейса — список из `GET /admin/cases` (статус не `draft`) → тело `{ case_id }`.

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
