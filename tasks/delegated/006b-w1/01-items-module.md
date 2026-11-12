# Цель
Создать общий модуль отрисовки скинов и карточек предметов `frontend/js/items.js` и его стили `frontend/css/items.css`. Ими будут пользоваться страницы инвентаря, кейсов, апгрейда, маркета и коллекций.

# Контекст
Прочитай сначала:
- `frontend/js/dom.js` — функция `h()`; DOM создаётся ТОЛЬКО через неё и `textContent`.
- `frontend/js/pieces.js` — `glyph(piece, color)`, `DEFAULT_PIECE_COLOR`.
- `frontend/js/format.js` — `PIECE_NAME_RU`, `fmtCrystals`.
- `frontend/css/base.css` — CSS-переменные (цвета `--panel`, `--line`, `--text`, `--muted`, `--gold`, `--mono`).
- `frontend/css/board.css` — как задаётся цвет глифа через `--piece-color` и тёмная обводка `text-shadow` (класс `.sq .glyph`).
- Образец стиля карточек: `legacy/templates/skins/item-cards.html` (только как картинка, код не копировать).

# Область
Создать ровно два файла:
- `frontend/js/items.js`
- `frontend/css/items.css`

Никакие другие файлы не трогать.

# Контракт
Объект `def` (скин) приходит с сервера в таком виде:
```json
{"id": 3, "code": "genesis-pawn-snow", "name": "Пешка | Снег", "kind": "piece_skin",
 "piece_type": "P", "rarity": "epic", "value": 500,
 "asset": {"type": "stub", "color": "#ffffff"},
 "collection": {"code": "genesis", "name": "Genesis"}}
```
Для `kind == "board_skin"`: `piece_type` равен `null`, а `asset` = `{"type": "stub", "light": "#ffffff", "dark": "#e5e5e5"}`.

`frontend/js/items.js` экспортирует ровно это:

```js
export const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic'];
export const RARITY_RU = {
  common: 'Обычный', uncommon: 'Необычный', rare: 'Редкий',
  epic: 'Эпический', legendary: 'Легендарный', mythic: 'Мифический',
};
export const EXTERIOR_RU = {
  FN: 'Прямо с завода', MW: 'Немного поношенное', FT: 'После полевых испытаний',
  WW: 'Поношенное', BS: 'Закалённое в боях',
};
export const SLOT_RU = {
  P: 'Пешка', N: 'Конь', B: 'Слон', R: 'Ладья', Q: 'Ферзь', K: 'Король', board: 'Доска',
};

export function skinPreview(def)
export function itemCard(def, opts = {})
```

`skinPreview(def)` возвращает `Node`:
- если `def.kind === 'piece_skin'`: `h('div', { class: 'skin-preview' }, glyphSpan)`, где `glyphSpan = h('span', { class: 'skin-glyph' }, glyph(def.piece_type, 'white'))`, и затем `glyphSpan.style.setProperty('--piece-color', def.asset.color)`;
- если `def.kind === 'board_skin'`: `h('div', { class: 'skin-preview' }, grid)`, где `grid = h('div', { class: 'skin-board' })` с 16 дочерними `h('span', { class: 'cell' })` (сетка 4×4). Затем `grid.style.setProperty('--light', def.asset.light)` и `grid.style.setProperty('--dark', def.asset.dark)`. Клетка с индексом `i` (0..15) получает дополнительный класс `dark`, если `(Math.floor(i / 4) + i) % 2 === 1`, иначе класс `light`.

`itemCard(def, opts)` возвращает `Node` — корневой `div`:
- классы: `item-card`, `r-<def.rarity>` (например `r-epic`); плюс `selected`, если `opts.selected === true`; плюс `clickable`, если передан `opts.onClick`;
- если передан `opts.onClick` — повесить `click` на корень (`addEventListener('click', opts.onClick)`) и добавить атрибуты `role: 'button'`, `tabindex: '0'`;
- содержимое строго в таком порядке:
  1. `skinPreview(def)`;
  2. `h('div', { class: 'item-name' }, def.name)`;
  3. `h('div', { class: 'item-meta' }, h('span', { class: 'item-rarity' }, RARITY_RU[def.rarity]), h('span', { class: 'item-value mono' }, fmtCrystals(def.value)))`;
  4. только если `opts.exterior` — строка: `h('div', { class: 'item-exterior' }, EXTERIOR_RU[opts.exterior] ?? opts.exterior)`;
  5. только если `opts.badge` — строка: `h('span', { class: 'item-badge' }, opts.badge)`;
  6. только если `opts.extra` — `Node`: добавить его последним как есть.

Импорты в `items.js` — только эти:
```js
import { h } from './dom.js';
import { glyph } from './pieces.js';
import { fmtCrystals } from './format.js';
```

`frontend/css/items.css` — ровно эти правила (значения дословно):
```css
.r-common    { --rarity: #9aa4b2; }
.r-uncommon  { --rarity: #38e8ff; }
.r-rare      { --rarity: #8b5cf6; }
.r-epic      { --rarity: #ffc93c; }
.r-legendary { --rarity: #ff7847; }
.r-mythic    { --rarity: #ff5470; }

.item-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }

.item-card { position: relative; display: flex; flex-direction: column; gap: 6px; padding: 12px;
  border-radius: 14px; border: 1px solid var(--line); border-top: 3px solid var(--rarity, var(--line));
  background: linear-gradient(180deg, color-mix(in srgb, var(--rarity, #000) 10%, var(--panel)), var(--panel)); }
.item-card.clickable { cursor: pointer; transition: transform .15s, box-shadow .15s; }
.item-card.clickable:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, .35); }
.item-card.selected { outline: 2px solid var(--gold); outline-offset: 2px; }

.skin-preview { display: grid; place-items: center; height: 84px; }
.skin-glyph { font-size: 56px; line-height: 1; color: var(--piece-color, #f4f6ff); text-shadow: 0 0 2px #000, 0 0 1px #000; }
.skin-board { display: grid; grid-template-columns: repeat(4, 16px); grid-template-rows: repeat(4, 16px);
  border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
.skin-board .cell.light { background: var(--light, #454f77); }
.skin-board .cell.dark { background: var(--dark, #262e4d); }

.item-name { font-weight: 700; font-size: 13.5px; color: var(--text); }
.item-meta { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; }
.item-rarity { color: var(--rarity, var(--muted)); font-weight: 600; }
.item-value { color: var(--gold); }
.item-exterior { font-size: 11.5px; color: var(--muted); }
.item-badge { position: absolute; top: 8px; right: 8px; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 700; background: rgba(0, 0, 0, .45); color: var(--gold); }
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK` и завершается с кодом 0.

# Нельзя
- Использовать `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `setAttribute('style', …)`, `Math.random`, `localStorage`.
- Добавлять экспорты, параметры или CSS-правила, которых нет в контракте.
- Менять любые файлы, кроме двух указанных.
- Если что-то в контракте не сходится с существующими модулями — не придумывать обход, а описать проблему в SUMMARY.
