# Цель
Отдельная вкладка админки «Кейсы»: кейсы не принадлежат коллекции, дропы из любых коллекций.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1, 5 «Кейс», 6.1 `AdminCaseOut`, 6.2, 6.3 «Админ»), `frontend/js/admin/cases.js` (текущий код — образец стиля карточек, модалок, таблицы дропов), `frontend/js/admin.js` (массив `TABS`), `frontend/js/admin/catalog.js` (функции `field`, `statusPill` — скопировать к себе, не импортировать).

# Область
`frontend/js/admin/cases.js` (переписать), `frontend/js/admin.js` (одна строка).

# Что сделать
1. `admin.js`: в `TABS` сразу после `catalog` вставить `{ key: 'cases', label: 'Кейсы', path: './admin/cases.js', fn: 'mount' },`. Больше ничего.
2. `cases.js`: удалить экспорт `renderCasesSection`; экспортировать `export async function mount(root)`, который вызывает `render(root)`.
3. `render(root)`: `clear(root)`; параллельно загрузить `GET /admin/cases`, `GET /admin/item-defs`, `GET /admin/collections`; ошибка → `toast(e.message, 'error')` и выход. Вывести: форму «Новый кейс» (поля «Код», «Название», «Цена» (по умолчанию 100), «Порядок» (0) → `POST /admin/cases` `{code, name, price, sort}`), затем карточки кейсов в порядке ответа; если кейсов нет — «Кейсов пока нет». После любого успешного действия — `toast('Готово', 'success')` и `render(root)`.
4. Карточка кейса: заголовок `cs.name` и статус-пилюля (`CASE_STATUS_RU = { draft: 'Черновик', active: 'Активен', closed: 'Закрыт' }`, класс `'pill status-' + cs.status`); строка `cs.code · цена <fmtCrystals(price)> · порядок <sort>`; строка коллекций: если `cs.collections.length === 0` — «Без дропов», если 1 — «Коллекция X», иначе «Смешанный: X, Y»; таблица дропов как сейчас (имя скина брать из `item-defs` по id; если не найден — «#<id>»), колонки «Скин», «Вес», «Шанс».
5. Кнопки карточки:
   - всегда «Изменить» → модалка с «Название», «Цена», «Порядок» → `PATCH /admin/cases/{id}`;
   - `draft`: «Автовеса», «Дропы вручную», «Активировать», «Удалить» (с `confirmModal`, `DELETE /admin/cases/{id}`);
   - `active`: «Закрыть» (`confirmModal('Закрыть кейс', 'Кейс перестанет открываться.', 'Закрыть', 'danger')` → `POST /admin/cases/{id}/close`);
   - `closed`: «Активировать».
   «Активировать» → `POST /admin/cases/{id}/activate`.
6. Модалка «Автовеса»: список чекбоксов по коллекциям со статусом не `retired` (подпись `name (code) — статус`), кнопка «Заполнить» → `POST /admin/cases/{id}/drops/auto` с `{ collection_ids: [...] }` (id выбранных, числа); если ничего не выбрано — `toast('Выберите хотя бы одну коллекцию', 'error')` и модалку не закрывать (`return false`).
7. Модалка «Дропы вручную»: таблица всех скинов из `/admin/item-defs`, сгруппированных по коллекции (строка-заголовок с именем коллекции), у каждого `input type=number min=0` веса (начальное значение — текущий вес из `cs.drops` или 0). «Сохранить» → `PUT /admin/cases/{id}/drops` с массивом `{ item_def_id, weight }` только для весов > 0; вес должен быть целым, иначе `toast('Вес должен быть целым числом ≥ 0', 'error')` и `return false`.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK`; `grep -n "is_active\|/collections/' + detail" frontend/js/admin/cases.js` ничего не находит.

# Правила фронта
- DOM только через `h()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты. Цвета — только `el.style.setProperty(...)`.
- Тексты интерфейса — по-русски, дословно как в задаче.
- Если что-то не сходится с контрактом или кодом — остановиться и описать проблему в SUMMARY, ничего не придумывать.
