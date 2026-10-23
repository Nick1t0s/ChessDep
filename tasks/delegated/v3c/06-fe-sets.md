# Цель
Публичные страницы наборов: список наборов и набор (коллекции + доски).

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 `PublicSetOut`, `SetDetailOut`, 6.3 `/sets`), `frontend/js/collections.js`, `frontend/js/collection.js`, `frontend/collections.html`, `frontend/collection.html`.

# Область
`frontend/js/collections.js`, `frontend/js/collection.js`, `frontend/collections.html`, `frontend/collection.html` (в HTML — только `<title>`).

# Что сделать
- `<title>`: `Наборы — ChessDep` и `Набор — ChessDep`.
- `collections.js`: `initLayout({ active: 'sets' })`; заголовок «Наборы»; `GET /sets`; карточка: название, описание, `'Коллекций: ' + collections_count + ' · Досок: ' + boards_count`, пометка «Снят с выпуска», если `status === 'retired'`; ссылка → `/collection.html?set=<code>`. Пусто — «Наборов пока нет.».
- `collection.js`: `initLayout({ active: 'sets' })`; параметр `set` → `GET /sets/{code}`; заголовок — имя набора, описание; для каждой коллекции — `h2` с именем, описание, две строки карточек `itemCard(def)` — «Белые» (первые 6) и «Чёрные» (последние 6); затем секция «Доски» (`itemCard(def)` каждой доски), если они есть. Ошибка 404 → «Набор не найден».

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
