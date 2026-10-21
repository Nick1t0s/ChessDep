# Аудит существующего фронта (site/, templates/, FILES.md, main.py)

Дата: 2026-10-21. Итог: **логику не использовать вообще, вёрстку и анимации брать как визуальный референс.** Всё переезжает в `legacy/` (task-001), новый фронт пишется в `frontend/` по разделу 10 ТЗ.

## 1. Критические проблемы `site/js/`

| # | Проблема | Где |
|---|---|---|
| 1 | Вся «база данных» (пользователи, балансы, инвентарь, история) лежит в `localStorage`. Сервера нет. | `site/js/common.js:54-58`, ключи `chessdep_users_v1`, `chessdep_session_v1` |
| 2 | Пароли хранятся **открытым текстом** в localStorage и сравниваются на клиенте. | `common.js` `defaultUser`, `login`, `changePass` |
| 3 | Роль `admin` лежит в localStorage: `users[x].role = 'admin'` ставится в devtools одной строкой. | `common.js` `register`, `isAdmin`, `guard` |
| 4 | Админом становится первый зарегистрированный аккаунт. | `common.js` `register` (`first`) |
| 5 | «Сессия» — это просто имя пользователя в localStorage, без токена. | `KEY_SESSION` |
| 6 | Все исходы считаются через `Math.random()` на клиенте: деп на доске, апгрейд, кейсы, слоты. | `board.js:143`, `upgrade.js:122`, `case.js:15`, `skin-case.js:13`, `slots.js:29` |
| 7 | Баланс меняет сам клиент (`CD.addBalance`), есть «депозит» по кнопке и промокод `LUDO`, который подсказан в тексте ошибки. | `deposit.js:33-64`, `inventory.js:73` |
| 8 | Админка правит игровой конфиг (стоимость, веса) в localStorage, это видно и подменяется любым. | `admin.js`, `CD.saveConfig` |
| 9 | XSS: данные пользователей (ник, email) вставляются через `innerHTML` (≈55 мест). Ник `<img onerror=…>` сработает в админке. | `admin.js`, `common.js renderNav`, `leaderboard.js` и др. |
| 10 | Шрифты грузятся с Google Fonts — противоречит CSP «только self». | все `site/*.html:7` |

## 2. Несоответствие игровой механике

- `site/board.html` + `board.js` — **это не шахматы**: фигуры из «резерва» ставятся на пустую доску, апгрейд срабатывает в момент постановки, ходов нет. Противник — статичный ряд.
- Ценности 10/30/60/120 вместо 1/3/5/9; есть выдуманные «ферзь×2» (240) и апгрейд в короля (400). По ТЗ короля депать нельзя, выше ферзя ничего нет.
- Фиксированные шансы `UPG` (22%/16%/9%/6%/4%) не связаны с ценностями. По ТЗ шанс = `v_from / v_to`.
- `upgrade.html` — апгрейд фигур вне партии из «склада». В ТЗ фигуры вне партии не существуют, деп бывает только на доске. Апгрейд вне партии существует только для **скинов**.

## 3. `templates/` (36 файлов)

Плюс: каждый файл самодостаточен, есть явное разделение «данные приходят из `ServerAPI.*`». Подход правильный.
Минусы:
- стабы сами решают исход через `Math.random` (`piece-tray.html:83`, `board-upgrade-fx.html:80`, `upgrade-linear-race.html:85`, `skin-tradeup.html:104`, `cases/*`), а филлеры лент генерирует фронт. По ТЗ ленту отдаёт сервер;
- захардкожены неверные данные: `match-hud.html` показывает конь→ферзь «30.7%» (должно быть 33.33%), FEN зашит константой;
- инлайн `<style>`/`<script>` — под CSP нового фронта придётся выносить в файлы.

### Вердикт по файлам
| Файл | Решение |
|---|---|
| `layout/board-skeleton.html` | **Взять** вёрстку доски (рендер клеток, координаты, подсветки sel/hint/last/check) |
| `chess/match-hud.html` | **Взять** раскладку игрового экрана (доска + боковая панель + лента) |
| `chess/board-upgrade-fx.html` | **Взять** анимацию морфинга глифа и fail-тряску (для депа); каскад ferz×2 — выкинуть |
| `chess/upgrade-linear-race.html` | **Взять** бар с win-зоной для анимации депа (позиция = `roll_value`); множители ×2/×4 выкинуть |
| `chess/chance-table.html` | Можно взять как подсказку «таблица шансов» (данные — с сервера) |
| `chess/piece-tray.html` | Не нужен (дока фигур вне доски нет) |
| `cases/case-strip-horizontal.html` | **Взять** ленту кейса (ленту и индекс отдаёт сервер) |
| `cases/case-strip-vertical*.html`, `multi-open-cases.html` | Не нужны в MVP |
| `layout/lobby-case-grid.html` | **Взять** сетку кейсов (без lock-уровней) |
| `layout/mobile-layout.html` | **Взять** таб-бар для мобилки |
| `skins/item-cards.html`, `skin-inventory.html`, `board-skins.html` | **Взять** карточки, инвентарь, превью досок |
| `skins/skin-detail.html` | Опционально (без истории цены) |
| `skins/skin-gallery.html` | Не нужен (магазина нет) |
| `skins/skin-tradeup.html`, `gift-flow.html`, `live-drops.html` | Вне скоупа |
| `wheels/wheel-conic-gradient.html` | **Взять** колесо апгрейда скинов (угол = `roll_value`) |
| `wheels/wheel-svg-sectors.html` | Не нужен |
| `fx/*` (modal-result, toast-stack, count-balance, confetti-burst) | **Взять** |
| `sheets/rarity-sheet.html`, `chess-glyphs-sheet.html` | **Взять** как справочник палитры/глифов |
| `slots/*`, `misc/*` (crash, mines, plinko, coinflip, daily-wheel, quests) | Вне скоупа |
| `templates/index.html` | Галерея, не нужна |

## 4. `site/` HTML и CSS
| Файл | Решение |
|---|---|
| `site/css/style.css` | **Взять** токены, кнопки, карточки, тосты, мобильные медиазапросы; Rubik заменить на `system-ui` |
| `site/css/{board,case,upgrade,inventory,leaderboard}.css` | Взять как основу соответствующих страниц |
| `site/css/{slots,deposit,skins}.css` | Не нужны |
| `site/{auth,index,profile,leaderboard,admin,upgrade,case,inventory}.html` | Разметку взять как основу, убрать инлайн-обработчики и Google Fonts |
| `site/{board,slots,deposit,skins,skin-case,history}.html` | Не нужны (`board` — неверная механика; история переезжает в профиль) |
| `site/js/*` | **Выкинуть полностью** |

## 5. Прочее
- `main.py` — сэмпл PyCharm «Hi, PyCharm», удалить.
- `FILES.md` — описывает старую структуру и содержит неверные утверждения («движок js уже вынес ключевые места…»). Удалить, актуальная документация — `docs/`.
