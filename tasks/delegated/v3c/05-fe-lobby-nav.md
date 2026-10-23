# Цель
Лобби: ежедневная награда вместо бонуса, понятная ошибка неполной экипировки; меню: «Магазин», «Наборы».

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 1 «Ежедневная награда», 6.1 `DailyRewardOut`/`DailyRewardClaimOut`, п. 7 «Лобби»), `frontend/js/index.js` (блок «4. Ежедневный бонус», поиск игры, инвайты), `frontend/js/layout.js`, `frontend/js/modal.js` (`openModal`).

# Область
`frontend/js/index.js`, `frontend/js/layout.js`.

# Что сделать
- `layout.js`: в `SECTIONS` и `TABBAR` подпись `'Кейсы'` → `'Магазин'` (путь и ключ прежние); в `SECTIONS` после «Магазин» вставить `['Наборы', '/collections.html', 'sets']`.
- `index.js`: заменить блок ежедневного бонуса целиком (кнопка, таймер, `renderDaily`, `POST /me/daily-bonus`, `daily_bonus_available_at`) на «Ежедневная награда»:
  - карточка `h3` «Ежедневная награда», строка `'Побед сегодня: ' + wins_today + ' / ' + wins_required`, кнопка `'Забрать'` (`btn btn-gold btn-block`), подпись под ней: если `claimed_today` — «Награда за сегодня получена», если не хватает побед — `'Победите ещё в ' + (wins_required - wins_today) + ' партиях'`;
  - загрузка `GET /me/daily-reward` при старте (для залогиненного); кнопка `disabled`, если `!available`;
  - клик → `POST /me/daily-reward` → `openModal({ title: 'Награда получена', body: h('div', {}, h('p', {}, 'Вам выпал кейс «' + out.case.name + '»')), actions: [{ label: 'Позже', kind: 'ghost' }, { label: 'Открыть', kind: 'gold', onClick: () => { location.href = '/case.html?item=' + encodeURIComponent(out.item.id); } }] })` (сверь параметры с `modal.js`), затем перезагрузить статус.
- Ошибки поиска игры и создания/принятия инвайта: если `e.code === 'LOADOUT_INCOMPLETE'` (проверь в `frontend/js/api.js`, как называется поле с кодом ошибки у исключения, и используй его) — вместо обычного тоста показать `toast(e.message + ' — откройте инвентарь', 'error')` и через `openModal` предложить кнопку «В инвентарь» → `/inventory.html`. Остальные ошибки — как сейчас.

# Готово, когда
`bash scripts/check_frontend.sh` → `frontend check: OK`; `grep -n "daily-bonus\|daily_bonus" frontend/js/index.js` ничего не находит.

# Общие правила фронта
- Контракт API: `docs/contracts-collections.md` (п. 6 — формы ответов, п. 7 — что показывать). Поля и пути — дословно оттуда.
- DOM только через `h()` / `clear()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты в HTML. Цвета — только `el.style.setProperty(...)`.
- Фронт ничего не вычисляет из игровой логики (шансы, доступность — только из ответов API).
- Ошибки API — `toast(e.message, 'error')`. Тексты — по-русски, дословно как в задаче.
- Общий модуль `frontend/js/items.js` (правится параллельно задачей 01) будет экспортировать: `RARITIES`, `RARITY_RU`, `EXTERIOR_RU`, `SLOT_RU` (ключи `wP`…`bK` и `board: 'Доска'`), `WHITE_SLOTS`, `BLACK_SLOTS`, `LOADOUT_SLOTS` (13), `SIDE_RU`, `KIND_RU = { piece: 'Фигура', board: 'Доска', case: 'Кейс' }`, `CASE_KIND_RU = { set: 'Набор', collection: 'Коллекция', custom: 'Особый' }`, `skinPreview(def)` (фигура или доска), `casePreview(caseRef)`, `itemCard(def, opts)` (как сейчас), `invItemCard(item, opts)` — карточка предмета инвентаря `ItemOut` (скин или кейс; opts как у `itemCard`).
- Менять только файлы из «Область». Проверка: `bash scripts/check_frontend.sh` → `frontend check: OK`.
- Если что-то не сходится — остановиться и описать в SUMMARY, не придумывать.
