# Цель
Инвентарь v3: 13 слотов, предупреждение о неполной экипировке, кейсы, базовые предметы.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 `ItemOut`, `LoadoutOut`; п. 7 «Инвентарь»), `frontend/js/inventory.js`.

# Область
Только `frontend/js/inventory.js`.

# Что сделать
- Импорт из `./items.js`: `invItemCard, SLOT_RU, WHITE_SLOTS, BLACK_SLOTS`.
- Экипировка: три ряда — «Белые» (`WHITE_SLOTS`), «Чёрные» (`BLACK_SLOTS`), «Доска» (`['board']`); слот рисуется `invItemCard(item, { extra: кнопка «Снять» })` или «Пусто». Над рядами — `h('p', { class: 'inv-warning' }, 'Экипируйте скины на все фигуры и доску — без этого нельзя играть')`, показывать только если `loadout.complete === false` (атрибут `hidden`).
- Фильтр вида (`kindSelect`, `aria-label` «Вид»): `''` «Все», `'piece'` «Фигуры», `'board'` «Доски», `'case'` «Кейсы» → параметр `kind`. Фильтр стороны убрать.
- Карточки предметов — `invItemCard(item, { badge })`, `badge`: `'На маркете'` если `listed`, `'Надето'` если `equipped_slot`, иначе `undefined` (тогда для базовых карточка сама покажет «Базовый").
- Действия: для `item.kind === 'case'` и `status === 'owned'`: «Открыть» → `location.href = '/case.html?item=' + encodeURIComponent(item.id)`, «Продать», «Подарить» (как сейчас для скинов). Для скинов: «Надеть» (если не надет) — слот `item.def.kind === 'board' ? 'board' : item.def.side + item.def.piece_type`; «Продать», «Подарить» — только если `!item.bound`. Логику модалок продажи/подарка не менять.

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
