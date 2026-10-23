# Цель
В `frontend/js/game.js` и `frontend/js/dep-fx.js` фигуры показывать PNG-картинками скинов через `pieceNode` из `pieces.js`; размеры — в `frontend/css/game.css`.

# Контекст
Прочитай: `docs/contracts-skins.md` §7, `frontend/js/pieces.js` (функция `pieceNode(loadout, piece, color, extraClass)` возвращает `<img class="piece-img extraClass">` либо запасной `<span class="extraClass">` с глифом).
Параллельно другой исполнитель добавляет в API доски (`createBoard` в board.js) метод `pieceElement(piece, color)` — возвращает готовый узел фигуры с классом `glyph`. board.js НЕ трогай, просто используй этот метод.
Правила фронта: DOM только через `h()`/`textContent`, без `innerHTML`.

# Область
Только `frontend/js/game.js`, `frontend/js/dep-fx.js`, `frontend/css/game.css`.

# Правки game.js (ровно 4)
1. Импорт `import { glyph, pieceColor } from './pieces.js';` → `import { glyph, pieceNode } from './pieces.js';`
2. В `renderPanels()` две строки
```js
      king.textContent = glyph('K', color);
      king.style.setProperty('--piece-color', pieceColor(loadout, 'K', color));
```
заменить на `      king.replaceChildren(pieceNode(loadout, 'K', color, 'p-king-img'));`
3. В `renderDepPanel()` строки
```js
        const g = h('span', { class: 'dep-row-glyph ' + (state.you === 'white' ? 'side-white' : 'side-black') }, glyph(target.piece, state.you));
        g.style.setProperty('--piece-color', pieceColor(state.players[state.you].loadout, target.piece, state.you));
```
заменить на `        const g = pieceNode(state.players[state.you].loadout, target.piece, state.you, 'dep-row-glyph');`
4. В `openPromotion()` строки
```js
      const g = h('span', { class: 'glyph ' + (state.you === 'white' ? 'side-white' : 'side-black') }, glyph(upper, state.you));
      g.style.setProperty('--piece-color', pieceColor(state.players[state.you].loadout, upper, state.you));
```
заменить на `      const g = pieceNode(state.players[state.you].loadout, upper, state.you, 'glyph');`

Строку заголовка с `glyph(depPiece.piece, state.you) + ' ' + …` НЕ трогать (там текст).

# Правки dep-fx.js (ровно 2)
1. Удалить строку `import { glyph } from './pieces.js';`
2. Блок
```js
    if (event.success && glyphEl !== null) {
      glyphEl.textContent = glyph(event.to, side);
      glyphEl.classList.add('newpop');
```
заменить на
```js
    if (event.success && glyphEl !== null) {
      const fresh = boardApi.pieceElement(event.to, side);
      fresh.classList.add('newpop');
      glyphEl.replaceWith(fresh);
```
(остальные строки ветки — `ring = …`, `sqEl.appendChild(ring);` — оставить как есть).

# Правки game.css
Добавить в конец файла:
```css
/* PNG-скины фигур (docs/contracts-skins.md) */
.p-king .piece-img { display: block; width: 28px; height: 28px; }
.p-king-img { color: var(--piece-color, var(--text)); }
.dep-row-glyph.piece-img { width: 28px; height: 28px; }
.promo-btn .piece-img { width: 40px; height: 40px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` → `frontend check: OK`; `grep -n "pieceColor" frontend/js/game.js frontend/js/dep-fx.js` пусто; `git diff --stat` — только три файла.

# Нельзя
Трогать board.js, pieces.js и любые другие файлы; менять остальной код. Если что-то не сходится — остановиться и описать в SUMMARY.
