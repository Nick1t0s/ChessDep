# Цель
Вкладка админки «Коллекции» под v2: коллекция создаётся сразу с 12 фигурами, кейсов в карточке коллекции нет.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 5, 6.1, 6.2, 6.3 «Админ», 7), `frontend/js/admin/catalog.js` (стиль — следовать ему: `field()`, `statusPill`, `openModal`, `confirmModal`, `toast`).
Из `frontend/js/items.js` (правится параллельно) будут: `SLOT_RU` (ключи `wP`…`bK`, значения «Белая пешка»…«Чёрный король»), `WHITE_SLOTS`, `BLACK_SLOTS`, `skinPreview(def)`, `RARITIES`, `RARITY_RU`.

# Область
Только `frontend/js/admin/catalog.js`.

# Что сделать
1. Удалить импорт `renderCasesSection` и блок `casesBox` в `renderDetail`. Удалить `kindRu`, `newSkinForm`, `deleteItemDef` и всё, что связано с досками (`lightIn`, `darkIn`, `board_skin`).
2. Список коллекций (`renderList`): убрать колонку/вывод `cases_count`, если он есть. Остальное прежнее.
3. Форма создания коллекции (`createCollectionForm`): поля «Код», «Название», «Описание» как сейчас, плюс таблица из 12 строк в порядке `[...WHITE_SLOTS, ...BLACK_SLOTS]`. Константы в начале файла:
```js
const DEFAULT_RARITY = { P: 'common', N: 'uncommon', B: 'uncommon', R: 'rare', Q: 'epic', K: 'legendary' };
const RARITY_VALUE = { common: 20, uncommon: 60, rare: 150, epic: 500, legendary: 1500, mythic: 5000 };
const DEFAULT_COLOR = { w: '#ffffff', b: '#ffc93c' };
```
   Строка таблицы для слота `slot` (`side = slot[0]`, `pt = slot[1]`): колонки «Фигура» (`SLOT_RU[slot]`, текст), «Редкость» (select из `RARITIES` с подписями `RARITY_RU`, значение `DEFAULT_RARITY[pt]`), «Ценность» (`input type=number min=1`, значение `RARITY_VALUE[DEFAULT_RARITY[pt]]`; при смене редкости в select значение ценности ставится в `RARITY_VALUE[новая]`), «Цвет» (`input type=text`, значение `DEFAULT_COLOR[side]`), «Цель апгрейда» (checkbox, отмечен).
   Отправка: `POST /admin/collections` с телом `{ code, name, description, pieces: [...] }`, где элемент pieces — `{ side, piece_type: pt, rarity, value: Number(...), asset: { type: 'stub', color }, is_upgrade_target }`. Перед отправкой проверить: ценность — целое ≥ 1, цвет соответствует `/^#[0-9a-fA-F]{6}$/`; иначе `toast('Строка «' + SLOT_RU[slot] + '»: проверьте ценность и цвет', 'error')` и не отправлять. После успеха — `toast('Готово', 'success')` и открыть деталь созданной коллекции (`renderDetail(root, created.id)`).
4. Деталь (`skinsSection`): заголовок «Скины (12)»; таблица колонок «Превью», «Фигура» (`SLOT_RU[def.side + def.piece_type]`), «Код», «Название», «Редкость», «Ценность», «Цель апгрейда», кнопка «Изменить». Скины выводить в том порядке, в каком пришли из API. Без формы «Новый скин» и без кнопки удаления скина.
5. Модалка правки (`openEditModal`): поля «Название», «Ценность», «Цвет фигуры», «Цель апгрейда», «Редкость» (только если `d.status === 'draft'`). `saveItemDef` шлёт `PATCH /admin/item-defs/{id}` с `{ name, value, asset: { type: 'stub', color }, is_upgrade_target }` и `rarity` только для черновика.
6. Действия коллекции (`actionsRow`, выпуск/снятие/удаление) — без изменений. Подтверждение снятия с выпуска дополнить текстом: «Все активные кейсы с её скинами будут закрыты.»

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK`; `grep -n "board\|kind ===\|renderCasesSection\|/items'" frontend/js/admin/catalog.js` не находит `board`, `def.kind`, `renderCasesSection`, `/items`.

# Правила фронта
- DOM только через `h()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты. Цвета — только `el.style.setProperty(...)`.
- Тексты интерфейса — по-русски, дословно как в задаче.
- Если что-то не сходится с контрактом или кодом — остановиться и описать проблему в SUMMARY, ничего не придумывать.
