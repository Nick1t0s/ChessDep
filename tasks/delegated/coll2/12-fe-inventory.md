# Цель
Инвентарь под 12 слотов и фильтр по стороне.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Экипировка», 6.1 `LoadoutOut`, 6.3 `/inventory`, п. 7), `frontend/js/inventory.js`.
Из `frontend/js/items.js` (правится параллельно другой задачей) будут экспортированы: `SLOT_RU` (ключи `wP`…`bK`), `WHITE_SLOTS`, `BLACK_SLOTS` (массивы по 6 слотов), `SIDE_RU = { w: 'Белые', b: 'Чёрные' }`.

# Область
Только `frontend/js/inventory.js`.

# Что сделать
- Импорт: `import { itemCard, SLOT_RU, WHITE_SLOTS, BLACK_SLOTS } from './items.js';`.
- Вместо одного `slotsGrid` — два: `whiteSlots` и `blackSlots` (оба `h('div', { class: 'inv-slots' })`). `equipCard` = `h('div', { class: 'card' }, h('h3', { class: 'card-title' }, 'Экипировка'), h('h4', {}, 'Белые'), whiteSlots, h('h4', {}, 'Чёрные'), blackSlots)`.
- `loadLoadout`: очистить оба грида; для `WHITE_SLOTS` заполнять `whiteSlots`, для `BLACK_SLOTS` — `blackSlots`; разметка одного слота прежняя (подпись `SLOT_RU[slot]`, карточка с кнопкой «Снять» или «Пусто»). Вынеси построение слота в функцию `slotEl(slot, item)`.
- `kindSelect` переименовать в `sideSelect`, `aria-label` «Сторона», опции: `''` «Все», `'w'` «Белые», `'b'` «Чёрные». В `loadItems`: `if (sideSelect.value) params.set('side', sideSelect.value);`.
- `equip(item)`: слот = `item.def.side + item.def.piece_type` (убрать ветку `board`).
- Остальное не менять.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и `grep -n "board\|kind" frontend/js/inventory.js` не находит упоминаний `board_skin`, `piece_skin`, `'board'`.

# Правила фронта
- DOM только через `h()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты. Цвета — только `el.style.setProperty(...)`.
- Фронт ничего не вычисляет из игровой логики, только показывает ответы API.
- Тексты интерфейса — по-русски, дословно как в задаче.
