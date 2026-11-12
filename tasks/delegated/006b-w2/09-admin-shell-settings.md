# Цель
Каркас админки с вкладками (модули вкладок подгружаются динамически), вкладка «Настройки» и общий CSS админки.

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
Создать или перезаписать: `frontend/admin.html` (сейчас там заглушка — заменить), `frontend/js/admin.js`, `frontend/js/admin/settings.js`, `frontend/css/admin.css`. Модули `frontend/js/admin/catalog.js`, `cases.js`, `users.js`, `misc.js` пишут другие исполнители — их НЕ создавать.

# Контракт
### admin.html
Каркас как у `index.html`: `<title>Админка — ChessDep</title>`, CSS: `base.css`, `layout.css`, `components.css`, `items.css`, `admin.css`; скрипт `js/admin.js`.

### js/admin.js
- `const me = await initLayout({ auth: 'required', active: '' })`; main `wrap-wide admin`. Если `me.role !== 'admin'` → `p` «Нет доступа» и выход.
- `h1.page-title` «Админка»; `div.admin-tabs` из кнопок в порядке: catalog «Коллекции», users «Пользователи», settings «Настройки», market «Маркет», audit «Журнал». Активная кнопка — `btn btn-gold btn-sm`, остальные `btn btn-ghost btn-sm`.
- Контейнер `div.admin-tab`.
- Открытие вкладки `key`: подсветить кнопку, `clear(container)`, `location.hash = key`, затем по таблице:

  | key | модуль | функция |
  |---|---|---|
  | catalog | `./admin/catalog.js` | `mount` |
  | users | `./admin/users.js` | `mount` |
  | settings | `./admin/settings.js` | `mount` |
  | market | `./admin/misc.js` | `mountMarket` |
  | audit | `./admin/misc.js` | `mountAudit` |

  `const mod = await import(path); await mod[fn](container);` в `try/catch` с тостом ошибки.
- Стартовая вкладка — из `location.hash` без `#`, если это один из ключей, иначе `catalog`.

### js/admin/settings.js
`export async function mount(root)`:
- `GET /admin/settings` → `[{key, value, default, updated_at, updated_by}]`.
- `table.admin-table` с колонками: Ключ (`span.mono`), Значение (`input type=text` с классом `set-input`, значение `JSON.stringify(value)`), По умолчанию (`span.admin-muted.mono` с `JSON.stringify(default)`), Изменено (дата или «—»), и кнопка `btn btn-gold btn-sm` «Сохранить».
- Сохранить: `JSON.parse(input.value)` в `try` (ошибка → `toast('Некорректный JSON', 'error')`); `PUT /admin/settings/<key>` тело `{value}` → `toast('Сохранено', 'success')` и обновить ячейку «Изменено» из ответа (ответ — тот же объект настройки).
- Импорты — только из `../api.js`, `../dom.js`, `../toast.js`.

### css/admin.css, дословно:
```css
.admin-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.admin-tab { margin-top: 8px; }
.admin-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.admin-table th, .admin-table td { padding: 7px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
.admin-table th { color: var(--muted); font-weight: 600; }
.admin-form { display: grid; gap: 10px; max-width: 520px; }
.admin-form input, .admin-form select, .admin-form textarea, .admin-table input, .admin-table select, .modal input, .modal select, .modal textarea { padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line); background: rgba(255,255,255,.03); color: var(--text); }
.admin-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.admin-section { margin-top: 20px; }
.admin-muted { color: var(--muted); font-size: 12px; }
.status-draft { color: #9aa4b2; }
.status-released { color: #4ade80; }
.status-retired { color: #ff7847; }
.set-input { width: 260px; font-family: var(--mono); }
.admin .card { margin-bottom: 14px; overflow-x: auto; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
