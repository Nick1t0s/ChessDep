# Цель
Общие модули отрисовки предметов и доски под v3.

# Контекст
Прочитай: `frontend/js/items.js`, `frontend/js/pieces.js`, `frontend/js/board.js`, `frontend/css/*.css` (классы `skin-board`, `skin-preview`, `item-card`), git-историю `items.js` (`git log -p -3 -- frontend/js/items.js`: там старая ветка превью доски — верни её).

# Область
`frontend/js/items.js`, `frontend/js/pieces.js`, `frontend/js/board.js`, `frontend/css/items.css` (если файла нет — тот css, где описан `.item-card`; только добавление правил).

# Что сделать
- `items.js`: экспорты ровно как в «Общие правила» ниже. `SLOT_RU` дополнить `board: 'Доска'`; `LOADOUT_SLOTS = [...WHITE_SLOTS, ...BLACK_SLOTS, 'board']`.
  - `skinPreview(def)`: `def.kind === 'board'` → сетка 4×4 `skin-board` (как в старом коде) с `--light`/`--dark` из `def.asset`; иначе глиф фигуры (как сейчас).
  - `casePreview(caseRef)`: `h('div', { class: 'skin-preview case-preview' }, h('span', { class: 'case-glyph' }, '▣'))`.
  - `invItemCard(item, opts = {})`: если `item.kind === 'case'` — карточка `h('div', { class: 'item-card r-case' + (opts.onClick ? ' clickable' : '') }, casePreview(item.case), h('div', { class: 'item-name' }, item.case.name), h('div', { class: 'item-meta' }, h('span', { class: 'item-rarity' }, 'Кейс')), badge, extra)` (badge/extra/onClick — как в `itemCard`); иначе `itemCard(item.def, { ...opts, exterior: item.exterior, badge: opts.badge ?? (item.bound ? 'Базовый' : null) })`.
- CSS: `.case-glyph { font-size: 44px; line-height: 1; color: var(--gold); }` и `.item-card.r-case { border-color: var(--gold); }` (если переменной `--gold` нет — используй ту, что используется для золотого цвета в css проекта).
- `pieces.js`: `boardColors(loadout)` — если `loadout?.board?.asset?.type === 'stub'` → `{ light, dark }` из asset, иначе `{ ...DEFAULT_BOARD }`.
- `board.js`: доска рисуется по `state?.players?.[state?.you]?.loadout ?? state?.players?.white?.loadout` (зритель — доска белых). Остальное не менять.

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
