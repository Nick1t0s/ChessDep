# Цель
Доска в `frontend/js/board.js` рисуется PNG-картинкой скина (с рамкой), фигуры — PNG-картинками; стили — в `frontend/css/board.css`.

# Контекст
Прочитай: `docs/contracts-skins.md` (§1, §7), `frontend/js/pieces.js` (готовые `pieceNode`, `boardUrl`), `frontend/js/board.js` и `frontend/css/board.css` целиком.
Правила фронта: DOM только через `h()`/`textContent`, без `innerHTML`; CSS-переменные — только `style.setProperty`.
Сейчас board.js импортирует `pieceColor`, `boardColors`, которых в pieces.js больше нет — это и чинишь.

# Область
Только `frontend/js/board.js` и `frontend/css/board.css`.

# Правки board.js
1. Импорт заменить на `import { pieceNode, boardUrl } from './pieces.js';`
2. В `createBoard` строку `container.appendChild(h('div', { class: 'board-zone' }, ranksCol, board, filesRow));` заменить на:
```js
  const zone = h('div', { class: 'board-zone' }, ranksCol, board, filesRow);
  container.appendChild(zone);
  let lastState = null;
```
3. Перед `function setGlyph` добавить:
```js
  // Узел фигуры с ключом: render не пересоздаёт его, если фигура и картинка не менялись.
  function makePiece(piece, color, loadout) {
    const node = pieceNode(loadout, piece, color, 'glyph');
    node.dataset.key = piece + '|' + color + '|' + (node.tagName === 'IMG' ? node.src : '');
    return node;
  }

  function pieceElement(piece, color) {
    return makePiece(piece, color, lastState?.players?.[color]?.loadout);
  }
```
4. Функцию `setGlyph` заменить целиком на:
```js
  function setGlyph(btn, name, piece, color, loadout) {
    let current = null;
    for (const child of btn.children) {
      if (child.classList.contains('glyph')) {
        current = child;
        break;
      }
    }
    if (piece === null) {
      if (current !== null) current.remove();
      btn.classList.remove('side-white', 'side-black');
      btn.setAttribute('aria-label', name + ', пусто');
      return;
    }
    const fresh = makePiece(piece, color, loadout);
    if (current === null) {
      btn.appendChild(fresh);
    } else if (current.dataset.key !== fresh.dataset.key) {
      current.replaceWith(fresh);
    }
    btn.classList.toggle('side-white', color === 'white');
    btn.classList.toggle('side-black', color === 'black');
    btn.setAttribute(
      'aria-label',
      name + ', ' + (color === 'white' ? 'белый' : 'чёрный') + ' ' + (PIECE_NAME_RU[piece] ?? '').toLowerCase()
    );
  }
```
5. В `render` строки
```js
    const colors = boardColors(state?.players?.[state?.you]?.loadout ?? state?.players?.white?.loadout);
    board.style.setProperty('--light', colors.light);
    board.style.setProperty('--dark', colors.dark);
```
заменить на:
```js
    lastState = state;
    const url = boardUrl(state?.players?.[state?.you]?.loadout ?? state?.players?.white?.loadout);
    zone.classList.toggle('skinned', url !== null);
    if (url !== null) board.style.setProperty('--board-image', 'url("' + url + '")');
    else board.style.removeProperty('--board-image');
```
(комментарий «Доска рисуется скином смотрящего…» над ними оставить).
6. Строку `return { render, squareEl, setOrientation, element: board, orientation: () => currentOrientation };` заменить на
`  return { render, squareEl, setOrientation, pieceElement, element: board, orientation: () => currentOrientation };`

# Правки board.css
Вставить сразу после правила `.sq .glyph { … }` (перед `.sq[target]`):
```css
.sq .piece-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}

/* Доска-картинка 1088×1088: рамка 32 px = 2.9412 % ширины (docs/contracts-skins.md). */
.board-zone.skinned {
  position: relative;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto;
  gap: 0;
}

.board-zone.skinned .board {
  grid-column: 1;
  grid-row: 1;
  box-sizing: border-box;
  padding: 2.9412%;
  border: none;
  border-radius: 0;
  background-image: var(--board-image);
  background-size: 100% 100%;
  background-repeat: no-repeat;
}

.board-zone.skinned .sq,
.board-zone.skinned .sq.light { background-color: transparent; }

.board-zone.skinned .ranks {
  position: absolute;
  left: 0;
  top: 2.9412%;
  bottom: 2.9412%;
  width: 2.9412%;
  z-index: 1;
  pointer-events: none;
}

.board-zone.skinned .files {
  position: absolute;
  left: 2.9412%;
  right: 2.9412%;
  bottom: 0;
  height: 2.9412%;
  z-index: 1;
  pointer-events: none;
}

.board-zone.skinned .ranks span,
.board-zone.skinned .files span {
  font-size: 9px;
  color: rgba(255, 255, 255, .85);
  text-shadow: 0 0 2px #000, 0 0 1px #000;
}
```

# Готово, когда
`bash scripts/check_frontend.sh` → `frontend check: OK`; `grep -n "pieceColor\|boardColors\|glyph(" frontend/js/board.js` ничего не находит; `git diff --stat` — только два файла.

# Нельзя
Трогать другие файлы и остальной код. Если что-то не сходится — остановиться и описать в SUMMARY.
