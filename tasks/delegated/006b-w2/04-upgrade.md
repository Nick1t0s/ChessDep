# Цель
Страница апгрейда скинов: выбор входных предметов и цели, предпросмотр шанса, колесо с вращением до выпавшего значения.

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
Создать: `frontend/upgrade.html`, `frontend/js/upgrade.js`, `frontend/css/upgrade.css`.

# Контракт
`initLayout({ auth: 'required', active: 'upgrade' })`, main `wrap-wide upgrade`, `<title>Апгрейд — ChessDep</title>`.

API:
- `GET /inventory?sort=value` → `Item[]`; брать только `status === 'owned'`. `Item` = `{id, def, wear, exterior, status: 'owned'|'listed', equipped_slot: 'P'|'N'|'B'|'R'|'Q'|'K'|'board'|null, source, acquired_at}`, где `def` — объект скина (см. `frontend/js/items.js`).
- `GET /item-defs?upgrade_target=true` → массив `def` (по возрастанию `value`).
- `POST /upgrade/preview` тело `{input_ids: number[], target_def_id}` → `{chance, chance_text, allowed, reason}`.
- `POST /upgrade` то же тело → `{success, chance, chance_text, roll_value, roll_id, burned_ids, item: Item|null}`.

Состояние в памяти: `selected` (Set id предметов, максимум 10), `target` (def или null), `rotation` (число градусов, начально 0), `previewSeq` (счётчик запросов).

Разметка: `h1.page-title` «Апгрейд»; `div.upg-layout` из трёх колонок:
1. `div.card` «Ваши предметы» — `p.upg-sum` («Выбрано: N · ценность <fmtCrystals(sum)>») и `div.item-grid` из `itemCard(item.def, { exterior: item.exterior, selected: selected.has(item.id), onClick })`. Клик переключает выбор; попытка выбрать 11-й → `toast('Не больше 10 предметов', 'error')`.
2. `div.card.upg-center`: `div.wheel-wrap` > (`div.wheel-pointer`, `div.wheel`); `div.upg-chance.mono` (текст шанса или «—»); `p.upg-reason` (причина недоступности); кнопка `btn btn-gold btn-block` «Апгрейд».
3. `div.card` «Цель» — `div.item-grid` из `itemCard(def, { selected: target?.id === def.id, onClick })`. Если выбраны предметы, показывать только цели с `def.value > sum`.

Предпросмотр: после любого изменения выбора или цели, если есть и предметы, и цель: `const seq = ++previewSeq; const p = await api('POST', '/upgrade/preview', ...); if (seq !== previewSeq) return;` затем:
- `wheel.style.setProperty('--win', (p.chance * 360) + 'deg')`;
- текст шанса `p.chance_text`;
- кнопка активна только при `p.allowed`;
- причина: `REASON_RU[p.reason] ?? ''`, где `REASON_RU = { UPGRADE_CHANCE_OUT_OF_RANGE: 'Шанс вне допустимого диапазона', TOO_MANY_INPUTS: 'Слишком много предметов', DUPLICATE_INPUTS: 'Повторяющиеся предметы', UPGRADE_TARGET_NOT_AVAILABLE: 'Цель недоступна' }`.

Если чего-то не хватает: `--win` = `0deg`, шанс «—», кнопка неактивна.

Апгрейд:
1. `confirmModal('Апгрейд', 'Все выбранные предметы сгорят при любом исходе. Шанс ' + chance_text + '.', 'Рискнуть', 'gold')`; отказ → выход.
2. Кнопка `disabled`; `res = await api('POST', '/upgrade', ...)`.
3. Вращение: `const base = Math.ceil(rotation / 360) * 360 + 1800; rotation = base + (360 - res.roll_value * 360);` `wheel.style.setProperty('transition', 'transform 4s cubic-bezier(.15,.85,.25,1)')`; `wheel.style.setProperty('transform', 'rotate(' + rotation + 'deg)')`. Дождаться `transitionend` (запасной `setTimeout` 4500 мс).
4. Успех → `openModal({ title: 'Апгрейд удался!', titleAnim: 'pop', body: itemCard(res.item.def, { exterior: res.item.exterior }), actions: [{ label: 'Отлично', kind: 'gold' }] })`. Провал → `openModal({ title: 'Не повезло', titleAnim: 'shake', body: h('p', { class: 'm-text' }, 'Предметы сгорели.'), actions: [{ label: 'Ок', kind: 'ghost' }] })`.
5. Очистить `selected` и `target`, перезагрузить инвентарь, сбросить предпросмотр.

`frontend/css/upgrade.css`, дословно:
```css
.upg-layout { display: grid; grid-template-columns: 1fr 300px 1fr; gap: 14px; align-items: start; }
@media (max-width: 900px) { .upg-layout { grid-template-columns: 1fr; } }
.upg-sum { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
.upg-center { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.wheel-wrap { position: relative; width: 220px; height: 220px; }
.wheel { --win: 0deg; width: 220px; height: 220px; border-radius: 50%; border: 3px solid var(--line);
  background: conic-gradient(var(--gold) 0deg var(--win), rgba(255,255,255,.07) var(--win) 360deg); }
.wheel-pointer { position: absolute; top: -6px; left: 50%; width: 0; height: 0; margin-left: -10px; z-index: 2;
  border-left: 10px solid transparent; border-right: 10px solid transparent; border-top: 18px solid var(--text); }
.upg-chance { font-size: 28px; font-weight: 800; color: var(--gold); }
.upg-reason { min-height: 18px; color: var(--muted); font-size: 12.5px; text-align: center; }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, атрибут `style=` и `on*=` в HTML, инлайн `<script>` и `<style>`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Цвета из данных — только `el.style.setProperty('--имя', значение)`.
- Менять любые файлы, кроме перечисленных в «Область» (в том числе `dom.js`, `api.js`, `layout.js`, `items.js`, общие CSS).
- Добавлять зависимости, сборку, сторонние библиотеки, внешние ссылки.
- Придумывать эндпоинты или поля, которых нет в «Контракт». Если чего-то не хватает — не обходить, а описать в SUMMARY.
