# Цель
Страницы маркета: лента лотов с фильтрами, сортировкой и покупкой, вкладка «Мои лоты», страница скина с лотами и историей продаж.

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
Создать: `frontend/market.html`, `frontend/market-item.html`, `frontend/js/market.js`, `frontend/js/market-item.js`, `frontend/css/market.css`.

# Контракт
`Listing` = `{id, price, status: 'active'|'sold'|'cancelled', created_at, closed_at, seller_login, mine: boolean, item: {id, def, wear, exterior}}`.

### market.html
`initLayout({ auth: 'optional', active: 'market' })`, main `wrap-wide market`, `<title>Маркет — ChessDep</title>`.
- `h1.page-title` «Маркет». Вкладки `div.mk-tabs` из двух кнопок: «Лоты», «Мои лоты» (вторая только если `me !== null`). Активная кнопка — класс `btn-gold`, неактивная — `btn-ghost`.
- **Лоты:** фильтры `div.mk-filters` из 4 `select`:
  - редкость: «Все» → '' плюс `RARITIES` с подписями `RARITY_RU`;
  - вид: «Все» → '', «Фигуры» → piece_skin, «Доски» → board_skin;
  - фигура: «Все» → '' плюс P, N, B, R, Q, K с подписями `PIECE_NAME_RU`;
  - сортировка: «Новые» → new, «Сначала дешёвые» → price_asc, «Сначала дорогие» → price_desc.

  Запрос `GET /market?page=<p>&limit=20&sort=<s>` плюс `&rarity=`, `&kind=`, `&piece_type=` только для непустых значений → `{items: Listing[], total}`. Смена фильтра сбрасывает страницу на 1.
  Показать `p.mk-total` «Найдено: <total>» и `div.item-grid`. Для каждого лота `itemCard(l.item.def, { exterior: l.item.exterior, badge: l.mine ? 'Ваш лот' : undefined, extra })`, где `extra` = `div.mk-row`:
  - `span.mk-price.mono` (`fmtCrystals(l.price)`);
  - `span.mk-seller` (`l.seller_login`);
  - кнопка `btn btn-gold btn-sm` «Купить» — только если `me !== null && !l.mine`;
  - ссылка `h('a', { href: '/market-item.html?def=' + l.item.def.id, class: 'btn btn-ghost btn-sm' }, 'История')`.

  Покупка: `confirmModal('Покупка', l.item.def.name + ' за ' + fmtCrystals(l.price), 'Купить', 'gold')` → `POST /market/listings/<id>/buy` → `toast('Куплено', 'success')`, `setBalance((await api('GET', '/me')).balance)`, перезагрузить ленту.
  Пагинация `div.mk-pager`: «Назад» (неактивна на 1-й), `span` «<page> / <pages>», «Вперёд» (неактивна на последней), где `pages = Math.max(1, Math.ceil(total / 20))`.
- **Мои лоты:** `select` статуса (Активные → active, Проданные → sold, Снятые → cancelled) и `GET /me/listings?status=<s>` → `Listing[]`. Сетка `itemCard` с `extra` = `div.mk-row`: цена, дата `created_at`, а для `active` кнопка `btn btn-ghost btn-sm` «Снять» → `DELETE /market/listings/<id>` → тост и перезагрузка. Пусто → `p` «Нет лотов».

### market-item.html
`initLayout({ auth: 'optional', active: 'market' })`, main `wrap-wide market-item`, `<title>Скин на маркете — ChessDep</title>`.
- `def` из `?def=`; не `/^\d+$/` → `p` «Некорректная ссылка».
- `GET /market/defs/<def>` → `{def, stats: {active_count, min_price, last_sale_price}, listings: Listing[], sales: [{price, closed_at}]}`.
- Разметка:
  - `div.mi-head`: `itemCard(def)` и `div.mi-stats` из трёх `p`: «Лотов: N», «Мин. цена: <fmtCrystals или —>», «Последняя продажа: <fmtCrystals или —>»;
  - карточка «Лоты»: `table.mk-table` с колонками Цена, Продавец, Износ (`EXTERIOR_RU[l.item.exterior]`), и кнопка «Купить» (те же условия и поведение, что на market.html; после покупки перезагрузить данные страницы);
  - карточка «История продаж»: `table.mk-table` с колонками Цена, Дата. Пусто → строка «Продаж ещё не было».

`frontend/css/market.css`, дословно:
```css
.market .card, .market-item .card { margin-bottom: 16px; }
.mk-tabs { display: flex; gap: 8px; margin-bottom: 14px; }
.mk-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.mk-filters select { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel); color: var(--text); }
.mk-total { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
.mk-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.mk-price { color: var(--gold); font-weight: 800; }
.mk-seller { color: var(--muted); font-size: 12px; }
.mk-pager { display: flex; gap: 10px; align-items: center; justify-content: center; margin-top: 14px; }
.mi-head { display: grid; grid-template-columns: 200px 1fr; gap: 16px; align-items: start; margin-bottom: 16px; }
@media (max-width: 640px) { .mi-head { grid-template-columns: 1fr; } }
.mi-stats p { margin-bottom: 6px; }
.mk-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.mk-table th, .mk-table td { padding: 8px; border-bottom: 1px solid var(--line); text-align: left; }
.mk-table th { color: var(--muted); font-weight: 600; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
