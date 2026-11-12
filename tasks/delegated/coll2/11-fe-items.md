# Цель
Карточка скина и цвета доски под v2: у скина есть сторона, скинов досок нет.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 `ItemDefOut`, п. 7), `frontend/js/items.js`, `frontend/js/pieces.js`.

# Область
`frontend/js/items.js`, `frontend/js/pieces.js`.

# Что сделать
- `pieces.js`: `boardColors(loadout)` → тело `return { ...DEFAULT_BOARD };` (параметр оставить, eslint-комментариев не добавлять). Остальное не менять.
- `items.js`:
  - `SLOT_RU` заменить на:
```js
export const SLOT_RU = {
  wP: 'Белая пешка', wN: 'Белый конь', wB: 'Белый слон', wR: 'Белая ладья', wQ: 'Белый ферзь', wK: 'Белый король',
  bP: 'Чёрная пешка', bN: 'Чёрный конь', bB: 'Чёрный слон', bR: 'Чёрная ладья', bQ: 'Чёрный ферзь', bK: 'Чёрный король',
};
export const WHITE_SLOTS = ['wP', 'wN', 'wB', 'wR', 'wQ', 'wK'];
export const BLACK_SLOTS = ['bP', 'bN', 'bB', 'bR', 'bQ', 'bK'];
export const SIDE_RU = { w: 'Белые', b: 'Чёрные' };
```
  - `skinPreview(def)`: удалить ветку `board_skin` целиком; глиф — `glyph(def.piece_type, def.side === 'b' ? 'black' : 'white')`.
- Проверь `grep -rn "SLOT_RU\|skinPreview" frontend/js`: другие файлы не меняй, их правят другие задачи.

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK`.

# Правила фронта
- DOM только через `h()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты. Цвета — только `el.style.setProperty(...)`.
- Фронт ничего не вычисляет из игровой логики, только показывает ответы API.
- Тексты интерфейса — по-русски, дословно как в задаче.
