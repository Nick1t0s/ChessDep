# Цель
Страница профиля: данные игрока, смена пароля, история партий и история операций с пагинацией, выход.

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
Создать: `frontend/profile.html`, `frontend/js/profile.js`, `frontend/css/profile.css`.

# Контракт
`initLayout({ auth: 'required', active: 'profile' })`, main `wrap-wide profile`, `<title>Профиль — ChessDep</title>`.

API:
- `me` из `initLayout`: `{id, login, role, balance, elo}`.
- `POST /me/password` тело `{old_password, new_password}` → 204.
- `GET /me/games?limit=20` и следующая страница `&before=<next_before>` (значение подставлять через `encodeURIComponent`) → `{items: [{id, opponent_login, color: 'white'|'black', result: 'white'|'black'|'draw'|null, end_reason, time_control, finished_at, elo_delta: number|null}], next_before: string|null}`.
- `GET /me/ledger?limit=20` и следующая страница `&cursor=<next_cursor>` → `{items: [{id, delta, balance_after, reason, ref, created_at}], next_cursor: number|null}`.
- `POST /auth/logout` → 204.

Разметка, карточки `.card` сверху вниз:
1. «Профиль»: строки `p.pf-row` из `span` (подпись) и `b` (значение): Логин, Elo, Баланс (`fmtCrystals`), Роль («Администратор» для `admin`, иначе «Игрок»). Кнопка `btn btn-ghost` «Выйти» → `POST /auth/logout`, затем `location.href = '/login.html'`.
2. «Смена пароля»: `form.pf-form` из двух `div.field` (`label` + `input type=password`; новый с `minlength=8 maxlength=128`) и кнопки `btn btn-gold` «Сменить». Новый пароль короче 8 символов → тост ошибки без запроса. Успех → `toast('Пароль изменён', 'success')` и очистить поля. Не забыть `event.preventDefault()`.
3. «Партии»: `table.pf-table` с колонками Дата, Соперник, Цвет («Белые» / «Чёрные»), Результат, Причина (`END_REASON_RU[end_reason] ?? ''`), Контроль, Elo.
   - Результат: `null` → «Отменена»; `'draw'` → «Ничья»; `=== color` → «Победа»; иначе «Поражение».
   - Elo: `null` → «—»; иначе со знаком (`+16` / `-16`).
   - Кнопка `btn btn-ghost btn-sm` «Ещё» видна, пока `next_before !== null`, и дописывает строки. Пусто → строка «Партий ещё не было».
4. «Операции»: `table.pf-table` с колонками Дата, Операция (`REASON_RU[reason] ?? reason`), Сумма (со знаком и `◈`; класс ячейки `pos` при `delta > 0`, иначе `neg`), Баланс (`fmtCrystals(balance_after)`). Кнопка «Ещё», пока `next_cursor !== null`.
   `REASON_RU = { signup_bonus: 'Бонус за регистрацию', daily_bonus: 'Ежедневный бонус', game_win: 'Победа в партии', game_draw: 'Ничья в партии', case_purchase: 'Покупка кейса', admin_adjust: 'Корректировка администратором', market_buy: 'Покупка на маркете', market_sale: 'Продажа на маркете' }`.

Каждую таблицу обернуть в `div.table-wrap` (горизонтальная прокрутка на мобилке).

`frontend/css/profile.css`, дословно:
```css
.profile .card { margin-bottom: 16px; }
.pf-row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.pf-row span { color: var(--muted); }
.pf-form { display: grid; gap: 10px; max-width: 360px; margin-top: 8px; }
.pf-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.pf-table th, .pf-table td { padding: 7px 8px; border-bottom: 1px solid var(--line); text-align: left; }
.pf-table th { color: var(--muted); font-weight: 600; }
.pf-table td.pos { color: #4ade80; }
.pf-table td.neg { color: #ff5470; }
.profile .table-wrap { overflow-x: auto; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
