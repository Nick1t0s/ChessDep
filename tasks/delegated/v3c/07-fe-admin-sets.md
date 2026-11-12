# Цель
Вкладка админки «Наборы»: наборы → коллекции (12 фигур) и доски.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5 «Набор», «Коллекция / доска», 6.1–6.3 админ), `frontend/js/admin/catalog.js` (текущий: форма коллекции из 12 строк, модалка правки скина — переиспользовать), `frontend/js/admin.js` (`TABS`).

# Область
`frontend/js/admin/catalog.js`, `frontend/js/admin.js` (одна строка).

# Что сделать
- `admin.js`: у вкладки `catalog` подпись `'Наборы'`.
- `catalog.js`:
  - Список (`GET /admin/sets`): таблица «Код», «Название», «Статус» (`draft` Черновик / `released` Выпущен / `retired` Снят), «Коллекций», «Досок», метка «Базовый» при `is_base`; клик → деталь. Форма «Новый набор»: код, название, описание → `POST /admin/sets` → открыть деталь.
  - Деталь (`GET /admin/sets/{id}`): заголовок + статус; действия: `draft` — «Выпустить» (`POST …/release`), «Удалить набор» (`confirmModal`, `DELETE`); `released` и не `is_base` — «Снять с выпуска» (`confirmModal` с текстом «Все кейсы в продаже с его скинами будут сняты с продажи.»). Базовому набору этих кнопок нет.
  - Секция «Коллекции»: для каждой — имя, код, таблица 12 скинов (как текущая таблица скинов: превью, фигура, код, название, редкость, ценность, цель апгрейда, «Изменить»); в `draft` — кнопка «Удалить коллекцию» (`DELETE /admin/collections/{id}`). В `draft` — форма «Новая коллекция» (текущая форма из 12 строк), но отправка → `POST /admin/sets/{setId}/collections`.
  - Секция «Доски»: таблица (превью `skinPreview`, код, название, редкость, ценность, «Изменить», в `draft` — «Удалить» → `DELETE /admin/item-defs/{id}`); в `draft` — форма «Новая доска»: код, название, редкость, ценность, светлые клетки (`#ffffff`), тёмные клетки (`#e5e5e5`), цель апгрейда → `POST /admin/sets/{setId}/boards` с `asset: { type: 'stub', light, dark }`; цвета проверять `/^#[0-9a-fA-F]{6}$/`.
  - Модалка «Изменить скин»: для доски — поля «Светлые клетки»/«Тёмные клетки» и `asset: { type: 'stub', light, dark }`; для фигуры — «Цвет фигуры» как сейчас; «Редкость» — только если набор `draft`.
  - После любого успешного действия — `toast('Готово', 'success')` и перерисовать текущий экран.

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
