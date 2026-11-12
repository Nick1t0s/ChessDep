# Цель
Страницы списка кейсов и открытия кейса с анимацией горизонтальной ленты.

# Контекст
Прочитай сначала (это образцы, им надо следовать):
- `frontend/index.html` и `frontend/js/index.js` — образец страницы: HTML-каркас, `initLayout`, создание `main` через `h()`.
- `frontend/js/dom.js` — `h(tag, attrs, ...children)`, `clear(el)`. DOM создаётся ТОЛЬКО через `h()` и `textContent`. Разрешённые атрибуты `h()`: class, id, type, disabled, title, href (только относительный `/...` или `#...`), value, name, role, tabindex, for, required, readonly, maxlength, minlength, autocomplete, placeholder, hidden, min, max, step, rows, checked, aria-*, data-*, onClick/onInput/onChange/onSubmit/onKeydown.
- `frontend/js/api.js` — `api(method, path, body)`; путь без `/api/v1`, например `api('GET', '/inventory')`. При ошибке бросает `ApiError` с полями `status`, `code`, `message` (сообщение уже по-русски).
- `frontend/js/layout.js` — `initLayout({ auth, active })` возвращает `me` (`{id, login, role, balance, elo, daily_bonus_available_at}`) или `null`; `setBalance(n)`.
- `frontend/js/toast.js` — `toast(message, kind)`, kind: `info` | `success` | `error`.
- `frontend/js/modal.js` — `openModal({ title, titleAnim: 'none', body, actions, dismissible })` возвращает функцию закрытия; `actions` — `[{ label, kind: 'gold'|'ghost'|'danger', onClick }]`, модалка закрывается после `onClick`, если он не вернул `false`. `confirmModal(title, text, okLabel, kind) → Promise<boolean>`.
- `frontend/js/format.js` — `fmtCrystals(n)`, `PIECE_NAME_RU`, `END_REASON_RU`.
- `frontend/js/items.js` — `itemCard(def, { exterior, badge, extra, selected, onClick })`, `skinPreview(def)`, `RARITIES`, `RARITY_RU`, `EXTERIOR_RU`, `SLOT_RU`. Стили — `frontend/css/items.css` (классы `.item-grid`, `.item-card`).
- Готовые CSS-классы: `.wrap-wide` (контейнер страницы), `.card`, `.card-title`, `.btn`, `.btn-gold`, `.btn-ghost`, `.btn-danger`, `.btn-sm`, `.btn-block`, `.field` (обёртка `label` + `input`), `.mono`, `.pill`, `.page-title`.

Общие правила для всех страниц:
- HTML-файл страницы — копия каркаса `frontend/index.html`: свой `<title>`, подключить `css/base.css`, `css/layout.css`, `css/components.css`, `css/items.css` и свой CSS-файл, ровно один `<script type="module" src="js/<страница>.js"></script>`, пустой `<body></body>`.
- Модуль страницы начинается с `const me = await initLayout({...})`, затем создаёт `const main = h('main', { class: 'wrap-wide <имя-страницы>' })` и `document.body.appendChild(main)`.
- Любой запрос — через `api()`. Ошибку показывать `toast(e.message, 'error')`.
- Даты: `new Date(iso).toLocaleString('ru-RU')`. Деньги: `fmtCrystals(n)`.
- Пользовательский текст (логины, записки, названия) вставлять только как дочерние строки `h()` или через `textContent`.

# Область
Создать: `frontend/cases.html`, `frontend/case.html`, `frontend/js/cases.js`, `frontend/js/case.js`, `frontend/css/cases.css`.

# Контракт
### cases.html
`initLayout({ auth: 'optional', active: 'cases' })`, main `wrap-wide cases`, `<title>Кейсы — ChessDep</title>`.
`GET /cases` → `[{id, code, name, price, collection: {code, name}}]`. Заголовок `page-title` «Кейсы», сетка `div.case-grid`, для каждого — `div.card.case-card`: `h3.card-title` (name), `p.case-collection` (`'Коллекция ' + collection.name`), `p.case-price.mono` (`fmtCrystals(price)`), ссылка `h('a', { href: '/case.html?id=' + id, class: 'btn btn-gold btn-block' }, 'Открыть')`. Пустой список → `p` «Кейсов пока нет.».

### case.html
`initLayout({ auth: 'required', active: 'cases' })`, main `wrap-wide case-page`, `<title>Кейс — ChessDep</title>`.
- `id` из `?id=`; если не `/^\d+$/` → `p` «Некорректная ссылка» и выход.
- `GET /cases/<id>` → `{id, code, name, price, collection, drops: [{def, weight, chance, chance_text}]}`.
- Разметка: `h1.page-title` (name); `div.card` с лентой: `div.strip-window` > (`div.strip-marker`, `div.strip-track`); под ней кнопка `btn btn-gold` «Открыть за <fmtCrystals(price)>». Ниже карточка «Содержимое»: `div.item-grid` из `itemCard(drop.def, { badge: drop.chance_text })` в порядке ответа.
- До открытия лента заполнена карточками содержимого (по одной на каждый дроп, каждая в `div.strip-cell`), без анимации.
- Открытие: кнопка `disabled`; `POST /cases/<id>/open` → `res = {item: Item, strip: number[60], win_index, defs: {"<defId>": def}, balance}`. `Item` = `{id, def, wear, exterior, status: 'owned'|'listed', equipped_slot: 'P'|'N'|'B'|'R'|'Q'|'K'|'board'|null, source, acquired_at}`, где `def` — объект скина (см. `frontend/js/items.js`).
  1. `clear(track)`; для каждого `defId` из `res.strip` добавить `h('div', { class: 'strip-cell' }, itemCard(res.defs[String(defId)]))`.
  2. `track.style.setProperty('transition', 'none')`; `track.style.setProperty('transform', 'translateX(0px)')`; прочитать `track.offsetWidth` (принудительный reflow).
  3. `const offset = res.win_index * 132 + 66 - windowEl.clientWidth / 2;` (ширина ячейки 120 px + промежуток 12 px = 132; `windowEl` — элемент `div.strip-window`).
  4. `track.style.setProperty('transition', 'transform 5.5s cubic-bezier(.12,.8,.18,1)')`; `track.style.setProperty('transform', 'translateX(' + (-offset) + 'px)')`.
  5. Дождаться `transitionend` на `track` (запасной `setTimeout` 6000 мс; что раньше).
  6. `setBalance(res.balance)`; `openModal({ title: 'Выпало!', titleAnim: 'pop', body: itemCard(res.item.def, { exterior: res.item.exterior }), actions: [{ label: 'В инвентарь', kind: 'ghost', onClick: () => { location.href = '/inventory.html'; } }, { label: 'Ещё раз', kind: 'gold' }] })`; кнопка снова активна.
- Ошибка открытия → тост, кнопка снова активна.

`frontend/css/cases.css`, дословно:
```css
.case-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.case-card { display: flex; flex-direction: column; gap: 8px; }
.case-collection { color: var(--muted); font-size: 13px; }
.case-price { color: var(--gold); font-size: 18px; font-weight: 800; }
.case-page .card { margin-bottom: 16px; }
.strip-window { position: relative; overflow: hidden; height: 190px; margin-bottom: 12px; border-radius: 12px; background: rgba(0,0,0,.25); }
.strip-marker { position: absolute; top: 0; bottom: 0; left: 50%; width: 3px; margin-left: -1px; background: var(--gold); box-shadow: 0 0 12px var(--gold); z-index: 2; }
.strip-track { display: flex; gap: 12px; padding: 10px 0; will-change: transform; }
.strip-cell { flex: 0 0 120px; width: 120px; }
.strip-cell .item-card { height: 170px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
