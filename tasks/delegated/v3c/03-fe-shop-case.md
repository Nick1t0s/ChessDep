# Цель
Магазин кейсов и страница кейса (содержимое/покупка/открытие своего кейса).

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 `ShopCaseOut`, `CaseDetailOut`, `CaseBuyOut`, `CaseOpenOut`; 6.3; п. 7 «Магазин», `/case.html`), `frontend/js/cases.js`, `frontend/js/case.js` (анимация ленты — сохранить), `frontend/cases.html`, `frontend/case.html`, `frontend/js/format.js` (`fmtCrystals`, форматирование дат — если есть).

# Область
`frontend/js/cases.js`, `frontend/js/case.js`, `frontend/cases.html`, `frontend/case.html` (в HTML менять только `<title>`).

# Что сделать
- `cases.html`: `<title>Магазин — ChessDep</title>`.
- `cases.js`: `initLayout({ active: 'cases' })` (как сейчас); заголовок «Магазин»; `GET /shop`; три секции в порядке «Наборы» (`kind === 'set'`), «Коллекции» (`collection`), «Особые» (`custom`); пустую секцию не показывать; если кейсов нет совсем — «Сейчас в магазине пусто.». Карточка: название; подпись `'Набор ' + c.set.name` / `'Коллекция ' + c.collection.name` / ничего; цена `fmtCrystals(c.price)`; если `c.stock_left !== null` — `'Осталось ' + c.stock_left`; если `c.sale_ends_at` — `'До ' + new Date(c.sale_ends_at).toLocaleString('ru-RU')`; кнопки «Купить» (`POST /cases/{id}/buy` → `toast('Кейс в инвентаре', 'success')`, обновить баланс в шапке так же, как это делает `market-item.js` после покупки, и перезагрузить список) и ссылка «Содержимое» → `/case.html?id=<id>`.
- `case.js`: два режима по query-параметрам.
  - `?id=` — `GET /cases/{id}`: название, подпись вида/источника, цена, лимиты (как в магазине), таблица/сетка дропов (`itemCard(d.def)` + `d.chance_text`); кнопка «Купить», только если `on_sale_now` (поведение — как в магазине); если не в продаже — `h('p', {}, 'Сейчас не продаётся')`.
  - `?item=` — открытие своего кейса: `GET /inventory?kind=case`, найти предмет с этим `id` и `status === 'owned'` (нет → «Кейс не найден» и ссылка в инвентарь); затем `GET /cases/{item.case.id}` для показа содержимого; кнопка «Открыть» → `POST /inventory/{item}/open` → проигрывание ленты (существующий код анимации, данные `strip`, `win_index`, `defs`, `item`) → модалка результата как сейчас (кнопки «В инвентарь» и вместо «Ещё раз» — «В магазин» → `/cases.html`).
  - без параметров — ссылка «В магазин».

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
